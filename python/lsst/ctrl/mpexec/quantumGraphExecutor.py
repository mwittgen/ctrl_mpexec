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

from __future__ import annotations

__all__ = ["QuantumExecutor", "QuantumGraphExecutor"]

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from .reports import QuantumReport, Report

if TYPE_CHECKING:
    from lsst.daf.butler import Butler, Quantum
    from lsst.pipe.base import QuantumGraph, TaskDef


class QuantumExecutor(ABC):
    """Class which abstracts execution of a single Quantum.

    In general implementation should not depend on execution model and
    execution should always happen in-process. Main reason for existence
    of this class is to provide do-nothing implementation that can be used
    in the unit tests.
    """

    @abstractmethod
    def execute(self, taskDef: TaskDef, quantum: Quantum, butler: Butler) -> Quantum:
        """Execute single quantum.

        Parameters
        ----------
        taskDef : `~lsst.pipe.base.TaskDef`
            Task definition structure.
        quantum : `~lsst.daf.butler.Quantum`
            Quantum for this execution.
        butler : `~lsst.daf.butler.Butler`
            Data butler instance

        Returns
        -------
        quantum : `Quantum`
            The quantum actually executed.  At present this quantum will
            contain only unresolved `DatasetRef` instances for output datasets,
            reflecting the state of the quantum just before it was run (but
            after any adjustments for predicted but now missing inputs).  This
            may change in the future to include resolved output `DatasetRef`
            objects.

        Notes
        -----
        Any exception raised by the task or code that wraps task execution is
        propagated to the caller of this method.
        """
        raise NotImplementedError()

    def getReport(self) -> Optional[QuantumReport]:
        """Return execution report from last call to `execute`.

        Returns
        -------
        report : `~lsst.ctrl.mpexec.QuantumReport`
            Structure describing the status of the execution of a quantum.
            `None` is returned if implementation does not support this
            feature.

        Raises
        ------
        RuntimeError
            Raised if this method is called before `execute`.
        """
        return None


class QuantumGraphExecutor(ABC):
    """Class which abstracts QuantumGraph execution.

    Any specific execution model is implemented in sub-class by overriding
    the `execute` method.
    """

    @abstractmethod
    def execute(self, graph: QuantumGraph, butler: Butler) -> None:
        """Execute whole graph.

        Implementation of this method depends on particular execution model
        and it has to be provided by a subclass. Execution model determines
        what happens here; it can be either actual running of the task or,
        for example, generation of the scripts for delayed batch execution.

        Parameters
        ----------
        graph : `~lsst.pipe.base.QuantumGraph`
            Execution graph.
        butler : `~lsst.daf.butler.Butler`
            Data butler instance
        """
        raise NotImplementedError()

    def getReport(self) -> Optional[Report]:
        """Return execution report from last call to `execute`.

        Returns
        -------
        report : `~lsst.ctrl.mpexec.Report`, optional
            Structure describing the status of the execution of a quantum
            graph. `None` is returned if implementation does not support
            this feature.

        Raises
        ------
        RuntimeError
            Raised if this method is called before `execute`.
        """
        return None
