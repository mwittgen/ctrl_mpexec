# This file is part of ctrl_mpexec.
#
# Developed for the LSST Data Management System.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import click

from lsst.daf.butler.cli.utils import MWOption, split_commas, unwrap


class show_option:  # noqa: N801

    defaultHelp = unwrap("""Dump various info to standard output.
        Possible items are: `config`, `config=[Task::]<PATTERN>` or
        `config=[Task::]<PATTERN>:NOIGNORECASE` to dump configuration fields
        possibly matching given pattern and/or task label; `history=<FIELD>` to
        dump configuration history for a field, field name is specified as
        [Task::][SubTask.]Field; `dump-config`, `dump-config=Task` to dump
        complete configuration for a task given its label or all tasks;
        `pipeline` to show pipeline composition; `graph` to show information
        about quanta; `workflow` to show information about quanta and their
        dependency; `tasks` to show task composition.""")

    defaultMetavar = "ITEM|ITEM=VALUE"

    def __init__(self, help=defaultHelp, metavar=defaultMetavar, multiple=False, required=False):
        self.callback = split_commas if multiple else None
        self.help = help
        self.metavar = metavar
        self.multiple = multiple
        self.required = required

    def __call__(self, f):
        return click.option("--show", cls=MWOption,
                            callback=self.callback,
                            help=self.help,
                            metavar=self.metavar,
                            multiple=self.multiple,
                            required=self.required)(f)
