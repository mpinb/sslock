"""build.py

Uses setuptools for compiling c/cpp modules and installing module.

Copyright (C) 2018-2023 Max Planck Institute for Neurobiology of Behavior

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
this program. If not, see <http://www.gnu.org/licenses/>.
"""

def build(setup_kwargs):

    setup_kwargs.update({
        "packages": setup_kwargs['packages'],
        "url": "https://github.com/mpinb/sslock",
        "long_description": "\nlow-level file locking for parallel access on gpfs (spectrum storage)\n",
    })
