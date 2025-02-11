# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
from __future__ import unicode_literals

from django.test import TestCase

from weblate.formats.base import EmptyFormat
from weblate.formats.exporters import (
    CSVExporter,
    MoExporter,
    PoExporter,
    PoXliffExporter,
    TBXExporter,
    XliffExporter,
    XlsxExporter,
)
from weblate.formats.helpers import BytesIOMode
from weblate.lang.models import Language, Plural
from weblate.trans.models import (
    Comment,
    Component,
    Dictionary,
    Project,
    Source,
    Suggestion,
    Translation,
    Unit,
)
from weblate.utils.state import STATE_EMPTY, STATE_TRANSLATED


def fake_get_comments():
    return [Comment(comment='Weblate translator comment')]


class PoExporterTest(TestCase):
    _class = PoExporter
    _has_context = True
    _has_comments = True

    def get_exporter(self, lang=None, **kwargs):
        if lang is None:
            lang, created = Language.objects.get_or_create(code='xx')
            if created:
                Plural.objects.create(language=lang)
        return self._class(
            language=lang,
            project=Project(slug='test', name='TEST'),
            **kwargs
        )

    def check_export(self, exporter):
        output = exporter.serialize()
        self.assertIsNotNone(output)
        return output

    def check_plurals(self, result):
        self.assertIn(b'msgid_plural', result)
        self.assertIn(b'msgstr[2]', result)

    def check_dict(self, word):
        exporter = self.get_exporter()
        exporter.add_dictionary(word)
        self.check_export(exporter)

    def test_dictionary(self):
        self.check_dict(Dictionary(source='foo', target='bar'))

    def test_dictionary_markup(self):
        self.check_dict(Dictionary(source='<b>foo</b>', target='<b>bar</b>'))

    def test_dictionary_special(self):
        self.check_dict(Dictionary(source='bar\x1e\x1efoo', target='br\x1eff'))

    def check_unit(self, nplurals=3, template=None, source_info=None, **kwargs):
        if source_info is None:
            source_info = {}
        if nplurals == 3:
            equation = 'n==0 ? 0 : n==1 ? 1 : 2'
        else:
            equation = '0'
        lang = Language.objects.create(
            code='zz',
        )
        plural = Plural.objects.create(
            language=lang,
            number=nplurals,
            equation=equation
        )
        project = Project(
            slug='test',
            source_language=Language.objects.get(code='en'),
        )
        component = Component(
            slug='comp',
            project=project,
            file_format='xliff',
            template=template
        )
        translation = Translation(
            language=lang,
            component=component,
            plural=plural,
        )
        # Fake file format to avoid need for actual files
        translation.store = EmptyFormat(BytesIOMode('', b''))
        unit = Unit(translation=translation, id_hash=-1, **kwargs)
        unit.__dict__['source_info'] = Source(**source_info)
        if source_info:
            unit.get_comments = fake_get_comments
            unit.__dict__['suggestions'] = [
                Suggestion(target='Weblate translator suggestion')
            ]
        exporter = self.get_exporter(lang, translation=translation)
        exporter.add_unit(unit)
        return self.check_export(exporter)

    def test_unit(self):
        self.check_unit(source='xxx', target='yyy')

    def test_unit_mono(self):
        self.check_unit(source='xxx', target='yyy', template='template')

    def test_unit_plural(self):
        result = self.check_unit(
            source='xxx\x1e\x1efff',
            target='yyy\x1e\x1efff\x1e\x1ewww',
            state=STATE_TRANSLATED,
        )
        self.check_plurals(result)

    def test_unit_plural_one(self):
        self.check_unit(
            nplurals=1,
            source='xxx\x1e\x1efff',
            target='yyy',
            state=STATE_TRANSLATED,
        )

    def test_unit_not_translated(self):
        self.check_unit(
            nplurals=1,
            source='xxx\x1e\x1efff',
            target='yyy',
            state=STATE_EMPTY,
        )

    def test_context(self):
        result = self.check_unit(
            source='foo',
            target='bar',
            context='context',
            state=STATE_TRANSLATED,
        )
        if self._has_context:
            self.assertIn(b'context', result)
        elif self._has_context is not None:
            self.assertNotIn(b'context', result)

    def test_extra_info(self):
        result = self.check_unit(
            source='foo',
            target='bar',
            context='context',
            state=STATE_TRANSLATED,
            source_info={
                'check_flags': 'max-length:200',
                'context': 'Context in Weblate',
            },
        )
        if self._has_context:
            self.assertIn(b'context', result)
        elif self._has_context is not None:
            self.assertNotIn(b'context', result)
        if self._has_comments:
            self.assertIn(b'Context in Weblate', result)
            self.assertIn(b'Weblate translator comment', result)
            self.assertIn(b'Suggested in Weblate', result)
            self.assertIn(b'Weblate translator suggestion', result)

    def setUp(self):
        self.exporter = self.get_exporter()

    def test_has_get_storage(self):
        self.assertTrue(hasattr(self.exporter, 'get_storage'))

    def test_has_setsourcelanguage(self):
        self.assertTrue(hasattr(self.exporter.storage, 'setsourcelanguage'))

    def test_has_settargetlanguage(self):
        self.assertTrue(hasattr(self.exporter.storage, 'settargetlanguage'))

    def test_has_unitclass(self):
        self.assertTrue(hasattr(self.exporter.storage, 'UnitClass'))

    def test_has_addunit(self):
        self.assertTrue(hasattr(self.exporter.storage, 'addunit'))


class PoXliffExporterTest(PoExporterTest):
    _class = PoXliffExporter
    _has_context = True

    def check_plurals(self, result):
        self.assertIn(b'[2]', result)


class XliffExporterTest(PoExporterTest):
    _class = XliffExporter
    _has_context = True

    def check_plurals(self, result):
        # Doesn't support plurals
        return


class TBXExporterTest(PoExporterTest):
    _class = TBXExporter
    _has_context = False

    def check_plurals(self, result):
        # Doesn't support plurals
        return


class MoExporterTest(PoExporterTest):
    _class = MoExporter
    _has_context = True
    _has_comments = False

    def check_plurals(self, result):
        self.assertIn(b'www', result)


class CSVExporterTest(PoExporterTest):
    _class = CSVExporter
    _has_context = True

    def check_plurals(self, result):
        # Doesn't support plurals
        pass

    def test_escaping(self):
        output = self.check_unit(
            source='=HYPERLINK("https://weblate.org/"&A1, "Weblate")',
            target='yyy',
        )
        self.assertIn(b'"\'=HYPERLINK', output)


class XlsxExporterTest(PoExporterTest):
    _class = XlsxExporter
    _has_context = False
    _has_comments = False

    def check_plurals(self, result):
        # Doesn't support plurals
        pass
