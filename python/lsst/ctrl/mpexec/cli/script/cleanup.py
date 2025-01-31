# This file is part of ctrl_mpexec.
#
# Developed for the LSST Data Management System.
# This product includes software developed by the LSST Project
# (http://www.lsst.org).
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


import re
from typing import Any

from lsst.daf.butler import Butler, CollectionType
from lsst.daf.butler.registry import CollectionTypeError, MissingCollectionError

from .confirmable import ConfirmableResult


class NoSuchCollectionFailure:
    def __init__(self, collection: str):
        self.collection = collection

    def __str__(self) -> str:
        return f'Did not find a collection named "{self.collection}"'


class NotChainedCollectionFailure:
    def __init__(self, collection: str, type: str):
        self.collection = collection
        self.type = type

    def __str__(self) -> str:
        return f'COLLECTION must be a CHAINED collection, "{self.collection}" is a "{self.type}" collection.'


class CleanupResult(ConfirmableResult):
    def __init__(self, butler_config: str):
        self.butler_config = butler_config
        self.runs_to_remove: list[str] = []
        self.others_to_remove: list[str] = []
        self.failure: Any = None

    def describe(self, will: bool) -> str:
        if self.can_continue:
            msg = "Will remove:" if will else "Removed:"
            msg += "\n"
            msg += f"  runs: {', '.join(self.runs_to_remove)}\n"
            msg += f"  others: {', '.join(self.others_to_remove)}"
        else:
            msg = "Did not find any collections to remove."
        return msg

    def on_confirmation(self) -> None:
        butler = Butler(self.butler_config, writeable=True)
        with butler.transaction():
            for collection in self.others_to_remove:
                butler.registry.removeCollection(collection)
            butler.removeRuns(self.runs_to_remove)

    @property
    def failed(self) -> bool:
        return self.failure is not None

    @property
    def describe_failure(self) -> str:
        return str(self.failure)

    @property
    def can_continue(self) -> bool:
        return bool(self.runs_to_remove) or bool(self.others_to_remove)


def cleanup(
    butler_config: str,
    collection: str,
) -> CleanupResult:
    """Remove collections that start with the same name as a CHAINED
    collection but are not members of that collection.

    Parameters
    ----------
    butler_config : str
        The path location of the gen3 butler/registry config file.
    collection : str
        The name of the chained collection.
    """
    butler = Butler(butler_config)
    result = CleanupResult(butler_config)
    try:
        to_keep = set(butler.registry.getCollectionChain(collection))
    except MissingCollectionError:
        result.failure = NoSuchCollectionFailure(collection)
        return result
    except CollectionTypeError:
        result.failure = NotChainedCollectionFailure(
            collection, butler.registry.getCollectionType(collection).name
        )
        return result
    regex = re.compile(collection + ".+")
    to_consider = set(butler.registry.queryCollections(regex))
    to_remove = to_consider - to_keep
    for r in to_remove:
        if butler.registry.getCollectionType(r) == CollectionType.RUN:
            result.runs_to_remove.append(r)
        else:
            result.others_to_remove.append(r)
    return result
