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

import os.path

import cairo
import gi
from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_text
from django.utils.formats import number_format
from django.utils.html import escape
from django.utils.translation import get_language, npgettext, pgettext
from django.utils.translation import ugettext as _
from django.utils.translation import ugettext_lazy

from weblate.fonts.utils import configure_fontconfig, render_size
from weblate.utils.site import get_site_url
from weblate.utils.stats import GlobalStats

gi.require_version("PangoCairo", "1.0")
gi.require_version("Pango", "1.0")
from gi.repository import Pango, PangoCairo  # noqa:E402,I001 isort:skip

COLOR_DATA = {
    'grey': (0, 0, 0),
    'white': (0, 0, 0),
    'black': (255, 255, 255),
    'graph': (255, 255, 255),
}

WIDGETS = {}


def register_widget(widget):
    """Register widget in dictionary."""
    WIDGETS[widget.name] = widget
    return widget


class Widget(object):
    """Generic widget class."""
    name = None
    verbose = ''
    colors = ()
    extension = 'png'
    content_type = 'image/png'
    order = 100
    show = True

    def __init__(self, obj, color=None, lang=None):
        """Create Widget object."""
        # Get object and related params
        self.obj = obj
        self.color = self.get_color_name(color)
        self.lang = lang

    def get_color_name(self, color):
        """Return color name based on allowed ones."""
        if color not in self.colors:
            return self.colors[0]
        return color


class ContentWidget(Widget):
    """Generic content widget class."""

    def __init__(self, obj, color=None, lang=None):
        """Create Widget object."""
        super(ContentWidget, self).__init__(obj, color, lang)
        # Get translation status
        if lang:
            stats = obj.stats.get_single_language_stats(lang)
        else:
            stats = obj.stats
        self.percent = stats.translated_percent

    def get_percent_text(self):
        return pgettext('Translated percents in widget', '{0}%').format(
            int(self.percent)
        )


class BitmapWidget(ContentWidget):
    """Base class for bitmap rendering widgets."""
    colors = ('grey', 'white', 'black')
    extension = 'png'
    content_type = 'image/png'
    order = 100
    show = True
    head_template = '<span letter_spacing="-1000"><b>{}</b></span>'
    foot_template = '<span letter_spacing="1000">{}</span>'
    font_size = 10
    offset = 0
    column_offset = 0
    lines = True

    def __init__(self, obj, color=None, lang=None):
        """Create Widget object."""
        super(BitmapWidget, self).__init__(obj, color, lang)
        # Get object and related params
        self.total = obj.stats.source_strings
        self.languages = obj.stats.languages
        self.params = self.get_text_params()

        # Set rendering variables
        self.draw = None
        self.width = 0

    def get_text_params(self):
        """Create dictionary used for text formatting."""
        return {
            'name': self.obj.name,
            'count': self.total,
            'languages': self.languages,
            'percent': self.percent,
        }

    def get_filename(self):
        """Return widgets filename."""
        return os.path.join(
            settings.STATIC_ROOT,
            'widget-images',
            '{widget}-{color}.png'.format(**{
                'color': self.color,
                'widget': self.name,
            })
        )

    def get_columns(self):
        raise NotImplementedError()

    def get_column_width(self, surface, columns):
        return surface.get_width() // len(columns)

    def get_column_fonts(self):
        return [
            Pango.FontDescription('Source Sans Pro {}'.format(self.font_size * 1.5)),
            Pango.FontDescription('Source Sans Pro {}'.format(self.font_size))
        ]

    def render_additional(self, ctx):
        return

    def render(self, response):
        """Render widget."""
        configure_fontconfig()
        surface = cairo.ImageSurface.create_from_png(self.get_filename())
        height = surface.get_height()
        ctx = cairo.Context(surface)

        columns = self.get_columns()
        column_width = self.get_column_width(surface, columns)

        fonts = self.get_column_fonts()

        for i, column in enumerate(columns):
            offset = self.offset
            for row, text in enumerate(column):
                layout = PangoCairo.create_layout(ctx)
                layout.set_font_description(fonts[row])

                # Set color and position
                ctx.move_to(self.column_offset + column_width * i, offset)
                ctx.set_source_rgb(*COLOR_DATA[self.color])

                # Add text
                layout.set_markup(text)
                layout.set_alignment(Pango.Alignment.CENTER)
                layout.set_width(column_width * Pango.SCALE)

                offset += layout.get_pixel_size().height

                # Render to cairo context
                PangoCairo.show_layout(ctx, layout)

            # Render column separators
            if self.lines and i > 0:
                ctx.new_path()
                ctx.set_source_rgb(*COLOR_DATA[self.color])
                ctx.set_line_width(0.5)
                ctx.move_to(column_width * i, self.offset)
                ctx.line_to(column_width * i, height - self.offset)
                ctx.stroke()

        self.render_additional(ctx)

        surface.write_to_png(response)


class SVGWidget(ContentWidget):
    """Base class for SVG rendering widgets."""
    extension = 'svg'
    content_type = 'image/svg+xml; charset=utf-8'
    template_name = ''

    def render(self, response):
        """Rendering method to be implemented."""
        raise NotImplementedError()


class RedirectWidget(Widget):
    """Generic redirect widget class."""
    show = False

    def redirect(self):
        """Redirect to matching SVG badge."""
        kwargs = {
            'project': self.obj.slug,
            'widget': 'svg',
            'color': 'badge',
            'extension': 'svg',
        }
        if self.lang:
            kwargs['lang'] = self.lang.code
            return reverse('widget-image', kwargs=kwargs)
        return reverse('widget-image', kwargs=kwargs)


@register_widget
class NormalWidget(BitmapWidget):
    name = '287x66'
    order = 110
    offset = 10
    verbose = ugettext_lazy('Big status badge')

    def get_columns(self):
        return [
            [
                self.head_template.format(
                    number_format(self.total, force_grouping=True)
                ),
                self.foot_template.format(npgettext(
                    "Label on enage page", "String", "Strings", self.total
                ).upper()),
            ],
            [
                self.head_template.format(
                    number_format(self.languages, force_grouping=True)
                ),
                self.foot_template.format(npgettext(
                    "Label on enage page", "Language", "Languages", self.languages
                ).upper()),
            ],
            [
                self.head_template.format(self.get_percent_text()),
                self.foot_template.format(_('Translated').upper()),
            ],
        ]


@register_widget
class SmallWidget(BitmapWidget):
    name = '88x31'
    order = 111
    font_size = 7
    verbose = ugettext_lazy('Small status badge')

    def get_columns(self):
        return [
            [
                self.head_template.format(self.get_percent_text()),
                self.foot_template.format(_('Translated').upper()),
            ],
        ]


@register_widget
class OpenGraphWidget(NormalWidget):
    name = 'open'
    colors = ('graph', )
    order = 120
    lines = False
    offset = 300
    font_size = 20
    column_offset = 265
    head_template = '<span letter_spacing="-1000">{}</span>'
    foot_template = '<span letter_spacing="2000">{}</span>'
    verbose = ugettext_lazy('Open Graph image')

    def get_column_width(self, surface, columns):
        return 230

    def get_column_fonts(self):
        return [
            Pango.FontDescription('Source Sans Pro {}'.format(42)),
            Pango.FontDescription('Source Sans Pro {}'.format(18))
        ]

    def get_title(self):
        return 'Project <b>{}</b>'.format(escape(self.obj.name))

    def render_additional(self, ctx):
        ctx.move_to(280, 170)
        layout = PangoCairo.create_layout(ctx)
        layout.set_font_description(
            Pango.FontDescription('Source Sans Pro {}'.format(52))
        )
        layout.set_markup(self.get_title())
        PangoCairo.show_layout(ctx, layout)


class SiteOpenGraphWidget(OpenGraphWidget):
    def __init__(self, obj=None, color=None, lang=None):
        super(SiteOpenGraphWidget, self).__init__(GlobalStats())

    def get_title(self):
        return '<b>{}</b>'.format(escape(settings.SITE_TITLE))

    def get_text_params(self):
        return {}


@register_widget
class BadgeWidget(RedirectWidget):
    """Legacy badge which used to render PNG."""
    name = 'status'
    colors = ('badge', )


@register_widget
class ShieldsBadgeWidget(RedirectWidget):
    """Legacy badge which used to redirect to shields.io."""
    name = 'shields'
    colors = ('badge', )


@register_widget
class SVGBadgeWidget(SVGWidget):
    name = 'svg'
    colors = ('badge', )
    order = 80
    template_name = 'badge.svg'
    verbose = ugettext_lazy('Status badge')

    def render(self, response):
        translated_text = _('translated')
        translated_width = render_size(
            "DejaVu Sans", Pango.Weight.NORMAL, 11, 0, translated_text
        )[0].width + 5

        percent_text = self.get_percent_text()
        percent_width = render_size(
            "DejaVu Sans", Pango.Weight.NORMAL, 11, 0, percent_text
        )[0].width + 5

        if self.percent >= 90:
            color = '#4c1'
        elif self.percent >= 75:
            color = '#dfb317'
        else:
            color = '#e05d44'

        response.write(render_to_string(
            self.template_name,
            {
                'translated_text': translated_text,
                'percent_text': percent_text,
                'translated_width': translated_width,
                'percent_width': percent_width,
                'width': translated_width + percent_width,
                'color': color,
                'translated_offset': translated_width // 2,
                'percent_offset': translated_width + percent_width // 2,
                'lang': get_language(),
            }
        ))


@register_widget
class MultiLanguageWidget(SVGWidget):
    name = 'multi'
    order = 81
    colors = ('auto', 'red', 'green', 'blue')
    template_name = 'multi-language-badge.svg'
    verbose = ugettext_lazy('Vertical multi language status widget')

    COLOR_MAP = {
        'red': '#fa3939',
        'green': '#3fed48',
        'blue': '#3f85ed',
        'auto': None,
    }

    def render(self, response):
        translations = []
        offset = 20
        color = self.COLOR_MAP[self.color]
        for stats in self.obj.stats.get_language_stats():
            language = stats.language
            percent = stats.translated_percent
            if self.color == 'auto':
                if percent >= 85:
                    color = '#2eccaa'
                elif percent >= 50:
                    color = '#38f'
                else:
                    color = '#f6664c'
            translations.append((
                # Language name
                force_text(language),
                # Translation percent
                int(percent),
                # Text y offset
                offset,
                # Bar y offset
                offset - 6,
                # Bar width
                int(percent * 1.5),
                # Bar color
                color,
                # Row URL
                get_site_url(reverse(
                    'project-language',
                    kwargs={'lang': language.code, 'project': self.obj.slug}
                )),
                # Top offset for horizontal
                10 + int((100 - percent) * 1.5),
            ))
            offset += 15

        response.write(render_to_string(
            self.template_name,
            {
                'height': len(translations) * 15 + 15,
                'translations': translations,
                'site_url': get_site_url(),
            }
        ))


@register_widget
class HorizontalMultiLanguageWidget(MultiLanguageWidget):
    name = 'horizontal'
    order = 82
    template_name = 'multi-language-badge-horizontal.svg'
    verbose = ugettext_lazy('Horizontal multi language status widget')
