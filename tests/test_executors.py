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
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Simple unit test for cmdLineFwk module.
"""

import logging
import networkx as nx
from multiprocessing import Manager
import psutil
import sys
import time
import unittest
import warnings

from lsst.ctrl.mpexec import MPGraphExecutor, MPGraphExecutorError, MPTimeoutError, QuantumExecutor
from lsst.ctrl.mpexec.execFixupDataId import ExecFixupDataId
from lsst.pipe.base import NodeId


logging.basicConfig(level=logging.DEBUG)

_LOG = logging.getLogger(__name__)


class QuantumExecutorMock(QuantumExecutor):
    """Mock class for QuantumExecutor
    """
    def __init__(self, mp=False):
        self.quanta = []
        if mp:
            # in multiprocess mode use shared list
            manager = Manager()
            self.quanta = manager.list()

    def execute(self, taskDef, quantum, butler):
        _LOG.debug("QuantumExecutorMock.execute: taskDef=%s dataId=%s", taskDef, quantum.dataId)
        if taskDef.taskClass:
            # only works for TaskMockMP class below
            taskDef.taskClass().runQuantum()
        self.quanta.append(quantum)

    def getDataIds(self, field):
        """Returns values for dataId field for each visited quanta"""
        return [quantum.dataId[field] for quantum in self.quanta]


class QuantumMock:
    def __init__(self, dataId):
        self.dataId = dataId

    def __eq__(self, other):
        return self.dataId == other.dataId

    def __hash__(self):
        # dict.__eq__ is order-insensitive
        return hash(tuple(sorted(kv for kv in self.dataId.items())))


class QuantumIterDataMock:
    """Simple class to mock QuantumIterData.
    """
    def __init__(self, index, taskDef, **dataId):
        self.index = index
        self.taskDef = taskDef
        self.quantum = QuantumMock(dataId)
        self.dependencies = set()
        self.nodeId = NodeId(index, "DummyBuildString")


class QuantumGraphMock:
    """Mock for quantum graph.
    """
    def __init__(self, qdata):
        self._graph = nx.DiGraph()
        previous = qdata[0]
        for node in qdata[1:]:
            self._graph.add_edge(previous, node)
            previous = node

    def __iter__(self):
        yield from nx.topological_sort(self._graph)

    def __len__(self):
        return len(self._graph)

    def findTaskDefByLabel(self, label):
        for q in self:
            if q.taskDef.label == label:
                return q.taskDef

    def getQuantaForTask(self, taskDef):
        nodes = self.getNodesForTask(taskDef)
        return {q.quantum for q in nodes}

    def getNodesForTask(self, taskDef):
        quanta = set()
        for q in self:
            if q.taskDef == taskDef:
                quanta.add(q)
        return quanta

    @property
    def graph(self):
        return self._graph

    def findCycle(self):
        return []

    def determineInputsToQuantumNode(self, node):
        result = set()
        for n in node.dependencies:
            for otherNode in self:
                if otherNode.index == n:
                    result.add(otherNode)
        return result


class TaskMockMP:
    """Simple mock class for task supporting multiprocessing.
    """
    canMultiprocess = True

    def runQuantum(self):
        _LOG.debug("TaskMockMP.runQuantum")
        pass


class TaskMockFail:
    """Simple mock class for task which fails.
    """
    canMultiprocess = True

    def runQuantum(self):
        _LOG.debug("TaskMockFail.runQuantum")
        raise ValueError("expected failure")


class TaskMockSleep:
    """Simple mock class for task which "runs" for some time.
    """
    canMultiprocess = True

    def runQuantum(self):
        _LOG.debug("TaskMockSleep.runQuantum")
        time.sleep(5.)


class TaskMockLongSleep:
    """Simple mock class for task which "runs" for very long time.
    """
    canMultiprocess = True

    def runQuantum(self):
        _LOG.debug("TaskMockLongSleep.runQuantum")
        time.sleep(100.)


class TaskMockNoMP:
    """Simple mock class for task not supporting multiprocessing.
    """
    canMultiprocess = False


class TaskDefMock:
    """Simple mock class for task definition in a pipeline.
    """
    def __init__(self, taskName="Task", config=None, taskClass=TaskMockMP, label="task1"):
        self.taskName = taskName
        self.config = config
        self.taskClass = taskClass
        self.label = label

    def __str__(self):
        return f"TaskDefMock(taskName={self.taskName}, taskClass={self.taskClass.__name__})"


class MPGraphExecutorTestCase(unittest.TestCase):
    """A test case for MPGraphExecutor class
    """

    def test_mpexec_nomp(self):
        """Make simple graph and execute"""

        taskDef = TaskDefMock()
        qgraph = QuantumGraphMock([
            QuantumIterDataMock(index=i, taskDef=taskDef, detector=i) for i in range(3)
        ])

        # run in single-process mode
        qexec = QuantumExecutorMock()
        mpexec = MPGraphExecutor(numProc=1, timeout=100, quantumExecutor=qexec)
        mpexec.execute(qgraph, butler=None)
        self.assertEqual(qexec.getDataIds("detector"), [0, 1, 2])

    def test_mpexec_mp(self):
        """Make simple graph and execute"""

        taskDef = TaskDefMock()
        qgraph = QuantumGraphMock([
            QuantumIterDataMock(index=i, taskDef=taskDef, detector=i) for i in range(3)
        ])

        methods = ["spawn"]
        if sys.platform == "linux":
            methods.append("fork")
            methods.append("forkserver")

        for method in methods:
            with self.subTest(startMethod=method):
                # run in multi-process mode, the order of results is not defined
                qexec = QuantumExecutorMock(mp=True)
                mpexec = MPGraphExecutor(numProc=3, timeout=100, quantumExecutor=qexec, startMethod=method)
                mpexec.execute(qgraph, butler=None)
                self.assertCountEqual(qexec.getDataIds("detector"), [0, 1, 2])

    def test_mpexec_nompsupport(self):
        """Try to run MP for task that has no MP support which should fail
        """

        taskDef = TaskDefMock(taskClass=TaskMockNoMP)
        qgraph = QuantumGraphMock([
            QuantumIterDataMock(index=i, taskDef=taskDef, detector=i) for i in range(3)
        ])

        # run in multi-process mode
        qexec = QuantumExecutorMock()
        mpexec = MPGraphExecutor(numProc=3, timeout=100, quantumExecutor=qexec)
        with self.assertRaises(MPGraphExecutorError):
            mpexec.execute(qgraph, butler=None)

    def test_mpexec_fixup(self):
        """Make simple graph and execute, add dependencies by executing fixup code
        """

        taskDef = TaskDefMock()

        for reverse in (False, True):
            qgraph = QuantumGraphMock([
                QuantumIterDataMock(index=i, taskDef=taskDef, detector=i) for i in range(3)
            ])

            qexec = QuantumExecutorMock()
            fixup = ExecFixupDataId("task1", "detector", reverse=reverse)
            mpexec = MPGraphExecutor(numProc=1, timeout=100, quantumExecutor=qexec,
                                     executionGraphFixup=fixup)
            mpexec.execute(qgraph, butler=None)

            expected = [0, 1, 2]
            if reverse:
                expected = list(reversed(expected))
            self.assertEqual(qexec.getDataIds("detector"), expected)

    def test_mpexec_timeout(self):
        """Fail due to timeout"""

        taskDef = TaskDefMock()
        taskDefSleep = TaskDefMock(taskClass=TaskMockSleep)
        qgraph = QuantumGraphMock([
            QuantumIterDataMock(index=0, taskDef=taskDef, detector=0),
            QuantumIterDataMock(index=1, taskDef=taskDefSleep, detector=1),
            QuantumIterDataMock(index=2, taskDef=taskDef, detector=2),
        ])

        # with failFast we'll get immediate MPTimeoutError
        qexec = QuantumExecutorMock(mp=True)
        mpexec = MPGraphExecutor(numProc=3, timeout=1, quantumExecutor=qexec, failFast=True)
        with self.assertRaises(MPTimeoutError):
            mpexec.execute(qgraph, butler=None)

        # with failFast=False exception happens after last task finishes
        qexec = QuantumExecutorMock(mp=True)
        mpexec = MPGraphExecutor(numProc=3, timeout=3, quantumExecutor=qexec, failFast=False)
        with self.assertRaises(MPTimeoutError):
            mpexec.execute(qgraph, butler=None)
        # We expect two tasks (0 and 2) to finish successfully and one task to
        # timeout. Unfortunately on busy CPU there is no guarantee that tasks
        # finish on time, so expect more timeouts and issue a warning.
        detectorIds = set(qexec.getDataIds("detector"))
        self.assertLess(len(detectorIds), 3)
        if detectorIds != {0, 2}:
            warnings.warn(f"Possibly timed out tasks, expected [0, 2], received {detectorIds}")

    def test_mpexec_failure(self):
        """Failure in one task should not stop other tasks"""

        taskDef = TaskDefMock()
        taskDefFail = TaskDefMock(taskClass=TaskMockFail)
        qgraph = QuantumGraphMock([
            QuantumIterDataMock(index=0, taskDef=taskDef, detector=0),
            QuantumIterDataMock(index=1, taskDef=taskDefFail, detector=1),
            QuantumIterDataMock(index=2, taskDef=taskDef, detector=2),
        ])

        qexec = QuantumExecutorMock(mp=True)
        mpexec = MPGraphExecutor(numProc=3, timeout=100, quantumExecutor=qexec)
        with self.assertRaises(MPGraphExecutorError):
            mpexec.execute(qgraph, butler=None)
        self.assertCountEqual(qexec.getDataIds("detector"), [0, 2])

    def test_mpexec_failure_dep(self):
        """Failure in one task should skip dependents"""

        taskDef = TaskDefMock()
        taskDefFail = TaskDefMock(taskClass=TaskMockFail)
        qdata = [
            QuantumIterDataMock(index=0, taskDef=taskDef, detector=0),
            QuantumIterDataMock(index=1, taskDef=taskDefFail, detector=1),
            QuantumIterDataMock(index=2, taskDef=taskDef, detector=2),
            QuantumIterDataMock(index=3, taskDef=taskDef, detector=3),
            QuantumIterDataMock(index=4, taskDef=taskDef, detector=4),
        ]
        qdata[2].dependencies.add(1)
        qdata[4].dependencies.add(3)
        qdata[4].dependencies.add(2)

        qgraph = QuantumGraphMock(qdata)

        qexec = QuantumExecutorMock(mp=True)
        mpexec = MPGraphExecutor(numProc=3, timeout=100, quantumExecutor=qexec)
        with self.assertRaises(MPGraphExecutorError):
            mpexec.execute(qgraph, butler=None)
        self.assertCountEqual(qexec.getDataIds("detector"), [0, 3])

    def test_mpexec_failure_failfast(self):
        """Fast fail stops quickly.

        Timing delay of task #3 should be sufficient to process
        failure and raise exception.
        """

        taskDef = TaskDefMock()
        taskDefFail = TaskDefMock(taskClass=TaskMockFail)
        taskDefLongSleep = TaskDefMock(taskClass=TaskMockLongSleep)
        qdata = [
            QuantumIterDataMock(index=0, taskDef=taskDef, detector=0),
            QuantumIterDataMock(index=1, taskDef=taskDefFail, detector=1),
            QuantumIterDataMock(index=2, taskDef=taskDef, detector=2),
            QuantumIterDataMock(index=3, taskDef=taskDefLongSleep, detector=3),
            QuantumIterDataMock(index=4, taskDef=taskDef, detector=4),
        ]
        qdata[1].dependencies.add(0)
        qdata[2].dependencies.add(1)
        qdata[4].dependencies.add(3)
        qdata[4].dependencies.add(2)

        qgraph = QuantumGraphMock(qdata)

        qexec = QuantumExecutorMock(mp=True)
        mpexec = MPGraphExecutor(numProc=3, timeout=100, quantumExecutor=qexec, failFast=True)
        with self.assertRaises(MPGraphExecutorError):
            mpexec.execute(qgraph, butler=None)
        self.assertCountEqual(qexec.getDataIds("detector"), [0])

    def test_mpexec_num_fd(self):
        """Check that number of open files stays reasonable
        """

        taskDef = TaskDefMock()
        qgraph = QuantumGraphMock([
            QuantumIterDataMock(index=i, taskDef=taskDef, detector=i) for i in range(20)
        ])

        this_proc = psutil.Process()
        num_fds_0 = this_proc.num_fds()

        # run in multi-process mode, the order of results is not defined
        qexec = QuantumExecutorMock(mp=True)
        mpexec = MPGraphExecutor(numProc=3, timeout=100, quantumExecutor=qexec)
        mpexec.execute(qgraph, butler=None)

        num_fds_1 = this_proc.num_fds()
        # They should be the same but allow small growth just in case.
        # Without DM-26728 fix the difference would be equal to number of
        # quanta (20).
        self.assertLess(num_fds_1 - num_fds_0, 5)


if __name__ == "__main__":
    unittest.main()
