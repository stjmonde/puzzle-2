# -*- coding: utf-8 -*-
import logging

from gemini import GeminiQuery

from puzzle.plugins import Plugin
from puzzle.models import (Variant, Genotype, Gene, Transcript, Case, Individual)

from . import (CaseMixin, VariantMixin)

logger = logging.getLogger(__name__)


class GeminiPlugin(CaseMixin, VariantMixin, Plugin):
    """This is the base class for puzzle plugins
        
        Args:
            db(str): Path to gemini database
            vtype: Variant type (snv or sv)
        
    """

    def __init__(self, db, vtype='snv'):
        super(GeminiPlugin, self).__init__()
        logger.debug("Setting self.db to {0}".format(db))
        self.db = db
        logger.debug("Setting variant type to {0}".format(vtype))
        self.variant_type = vtype

        logger.info("Check if database if in correct format")
        self.test_gemini_db()

        self.individuals = self._get_individuals()
        self.case_objs = self._get_cases(self.individuals)

    def test_gemini_db(self):
        """Check if self.db is a valid gemini database"""
        gq = GeminiQuery(self.db)
        return

    def init_app(self, app):
        """Initialize plugin via Flask."""

        logger.debug("Setting can_filter_gene to 'True'")
        self.can_filter_gene = True
        # logger.debug("Setting can_filter_sv to 'True'")
        # self.can_filter_sv = True
        # logger.debug("Setting can_filter_sv_len to 'True'")
        # self.can_filter_sv_len = True
        logger.debug("Setting can_filter_frequency to 'True'")
        self.can_filter_frequency = True
        logger.debug("Setting can_filter_cadd to 'True'")
        self.can_filter_cadd = True
        logger.debug("Setting can_filter_consequence to 'True'")
        self.can_filter_consequence = True
