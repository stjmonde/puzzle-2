# -*- coding: utf-8 -*-
"""
puzzle.plugins.sql.store
~~~~~~~~~~~~~~~~~~
"""
import logging
import os

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.sql.expression import ClauseElement

from puzzle.models import Case as BaseCase
from puzzle.models import Individual as BaseIndividual
from puzzle.models.sql import (BASE, Case, Individual)
from puzzle.plugins import VcfPlugin, GeminiPlugin, Plugin

logger = logging.getLogger(__name__)


class Store(Plugin):

    """SQLAlchemy-based database object.
    .. note::
        For testing pourposes use ``:memory:`` as the ``path`` argument to
        set up in-memory (temporary) database.
    Args:
        uri (Optional[str]): path/URI to the database to connect to
        debug (Optional[bool]): whether to output logging information
    Attributes:
        uri (str): path/URI to the database to connect to
        engine (class): SQLAlchemy engine, defines what database to use
        session (class): SQLAlchemy ORM session, manages persistance
        query (method): SQLAlchemy ORM query builder method
        classes (dict): bound ORM classes
    """

    def __init__(self, uri=None, debug=False, vtype='snv'):
        super(Store, self).__init__()
        self.uri = uri
        if uri:
            self.connect(uri, debug=debug)
        self.variant_type = vtype

        # ORM class shortcuts to enable fetching models dynamically
        # self.classes = {'gene': Gene, 'transcript': Transcript,
        #                 'exon': Exon, 'sample': Sample}

    def init_app(self, app):
        pass

    def connect(self, db_uri, debug=False):
        """Configure connection to a SQL database.

        Args:
            db_uri (str): path/URI to the database to connect to
            debug (Optional[bool]): whether to output logging information
        """
        kwargs = {'echo': debug, 'convert_unicode': True}
        # connect to the SQL database
        if 'mysql' in db_uri:
            kwargs['pool_recycle'] = 3600
        elif '://' not in db_uri:
            logger.debug("detected sqlite path URI: {}".format(db_uri))
            db_path = os.path.abspath(os.path.expanduser(db_uri))
            db_uri = "sqlite:///{}".format(db_path)

        self.engine = create_engine(db_uri, **kwargs)
        logger.debug('connection established successfully')
        # make sure the same engine is propagated to the BASE classes
        BASE.metadata.bind = self.engine
        # start a session
        self.session = scoped_session(sessionmaker(bind=self.engine))
        # shortcut to query method
        self.query = self.session.query
        return self

    @property
    def dialect(self):
        """Return database dialect name used for the current connection.
        Dynamic attribute.
        Returns:
            str: name of dialect used for database connection
        """
        return self.engine.dialect.name

    def set_up(self, reset=False):
        """Initialize a new database with the default tables and columns.
        Returns:
            Store: self
        """
        if reset:
            self.tear_down()

        # create the tables
        BASE.metadata.create_all(self.engine)
        return self

    def tear_down(self):
        """Tear down a database (tables and columns).
        Returns:
            Store: self
        """
        # drop/delete the tables
        logger.info('resetting database...')
        BASE.metadata.drop_all(self.engine)
        return self

    def save(self):
        """Manually persist changes made to various elements. Chainable.

        Returns:
            Store: ``self`` for chainability
        """
        # commit/persist dirty changes to the database
        self.session.flush()
        self.session.commit()
        return self

    def add_case(self, case_obj, vtype='snv', mode='vcf', ped_svg=None):
        """Load a case with individuals.

        Args:
            case_obj (puzzle.models.Case): initialized case model
        """
        new_case = Case(case_id=case_obj['case_id'],
                        name=case_obj['name'],
                        variant_source=case_obj['variant_source'],
                        variant_type=vtype,
                        variant_mode=mode,
                        pedigree=ped_svg)

        # build individuals
        inds = [Individual(
            ind_id=ind['ind_id'],
            mother=ind['mother'],
            father=ind['father'],
            sex=ind['sex'],
            phenotype=ind['phenotype'],
            ind_index=ind['index'],
            variant_source=ind['variant_source'],
            bam_path=ind['bam_path'],
        ) for ind in case_obj['individuals']]

        new_case.individuals = inds
        self.session.add(new_case)
        self.save()
        return new_case

    def delete_case(self, case_obj):
        """Delete a case from the database

        Args:
            case_obj (puzzle.models.Case): initialized case model
        """
        for ind_obj in case_obj.individuals:
            self.delete_individual(ind_obj)
        logger.info("Deleting case {0} from database".format(case_obj.case_id))
        self.session.delete(case_obj)
        self.save()
        return case_obj

    def delete_individual(self, ind_obj):
        """Delete a case from the database

        Args:
            ind_obj (puzzle.models.Individual): initialized individual model
        """
        logger.info("Deleting individual {0} from database".format(ind_obj.ind_id))
        self.session.delete(ind_obj)
        self.save()
        return ind_obj

    def case(self, case_id):
        """Fetch a case from the database."""
        case_obj = self.query(Case).filter_by(case_id=case_id).first()
        if case_obj is None:
            case_obj = BaseCase(case_id='unknown')
        return case_obj

    def individual(self, ind_id):
        """Fetch a case from the database."""
        ind_obj = self.query(Individual).filter_by(ind_id=ind_id).first()
        if ind_obj is None:
            ind_obj = BaseIndividual(ind_id='unknown')
        return ind_obj

    def cases(self):
        """Fetch all cases from the database."""
        return self.query(Case)

    def individuals(self, ind_ids=None):
        """Fetch all individuals from the database."""
        query = self.query(Individual)
        if ind_ids:
            query = query.filter(Individual.ind_id.in_(ind_ids))
        return query

    def variants(self, case_id, skip=0, count=30, filters=None):
        """Fetch variants for a case."""
        logger.debug("Fetching case with case_id:{0}".format(case_id))
        case_obj = self.case(case_id)
        plugin, case_id = select_plugin(case_obj)
        self.filters = plugin.filters
        variants = plugin.variants(case_id, skip, count, filters)
        return variants

    def variant(self, case_id, variant_id):
        """Fetch a single variant from variant source."""
        case_obj = self.case(case_id)
        plugin, case_id = select_plugin(case_obj)
        variant = plugin.variant(case_id, variant_id)
        return variant


def select_plugin(case_obj):
    """Select and initialize the correct plugin for the case."""
    if case_obj.variant_mode == 'vcf':
        logger.debug("Using vcf plugin")
        plugin = VcfPlugin(root_path=case_obj.variant_source,
                           vtype=case_obj.variant_type)
        plugin.case_objs = [case_obj]
    elif case_obj.variant_mode == 'gemini':
        logger.debug("Using gemini plugin")
        plugin = GeminiPlugin(db=case_obj.variant_source,
                              vtype=case_obj.variant_type)

    case_id = case_obj.case_id
    return plugin, case_id