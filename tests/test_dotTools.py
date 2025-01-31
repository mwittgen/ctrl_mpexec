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

"""Simple unit test for Pipeline.
"""

import io
import re
import unittest

import lsst.pipe.base.connectionTypes as cT
import lsst.utils.tests
from lsst.ctrl.mpexec.dotTools import pipeline2dot
from lsst.pipe.base import Pipeline, PipelineTask, PipelineTaskConfig, PipelineTaskConnections


class ExamplePipelineTaskConnections(PipelineTaskConnections, dimensions=()):
    input1 = cT.Input(
        name="", dimensions=["visit", "detector"], storageClass="example", doc="Input for this task"
    )
    input2 = cT.Input(
        name="", dimensions=["visit", "detector"], storageClass="example", doc="Input for this task"
    )
    output1 = cT.Output(
        name="", dimensions=["visit", "detector"], storageClass="example", doc="Output for this task"
    )
    output2 = cT.Output(
        name="", dimensions=["visit", "detector"], storageClass="example", doc="Output for this task"
    )

    def __init__(self, *, config=None):
        super().__init__(config=config)
        if not config.connections.input2:
            self.inputs.remove("input2")
        if not config.connections.output2:
            self.outputs.remove("output2")


class ExamplePipelineTaskConfig(PipelineTaskConfig, pipelineConnections=ExamplePipelineTaskConnections):
    pass


def _makeConfig(inputName, outputName, pipeline, label):
    """Factory method for config instances

    inputName and outputName can be either string or tuple of strings
    with two items max.
    """
    if isinstance(inputName, tuple):
        pipeline.addConfigOverride(label, "connections.input1", inputName[0])
        pipeline.addConfigOverride(label, "connections.input2", inputName[1] if len(inputName) > 1 else "")
    else:
        pipeline.addConfigOverride(label, "connections.input1", inputName)

    if isinstance(outputName, tuple):
        pipeline.addConfigOverride(label, "connections.output1", outputName[0])
        pipeline.addConfigOverride(label, "connections.output2", outputName[1] if len(outputName) > 1 else "")
    else:
        pipeline.addConfigOverride(label, "connections.output1", outputName)


class ExamplePipelineTask(PipelineTask):
    ConfigClass = ExamplePipelineTaskConfig


def _makePipeline(tasks):
    """Generate Pipeline instance.

    Parameters
    ----------
    tasks : list of tuples
        Each tuple in the list has 3 or 4 items:
        - input DatasetType name(s), string or tuple of strings
        - output DatasetType name(s), string or tuple of strings
        - task label, string
        - optional task class object, can be None

    Returns
    -------
    Pipeline instance
    """
    pipe = Pipeline("test pipeline")
    for task in tasks:
        inputs = task[0]
        outputs = task[1]
        label = task[2]
        klass = task[3] if len(task) > 3 else ExamplePipelineTask
        pipe.addTask(klass, label)
        _makeConfig(inputs, outputs, pipe, label)
    return list(pipe.toExpandedPipeline())


class DotToolsTestCase(unittest.TestCase):
    """A test case for dotTools"""

    def testPipeline2dot(self):
        """Tests for dotTools.pipeline2dot method"""
        pipeline = _makePipeline(
            [
                ("A", ("B", "C"), "task0"),
                ("C", "E", "task1"),
                ("B", "D", "task2"),
                (("D", "E"), "F", "task3"),
                ("D.C", "G", "task4"),
                ("task3_metadata", "H", "task5"),
            ]
        )
        file = io.StringIO()
        pipeline2dot(pipeline, file)

        # It's hard to validate complete output, just checking few basic
        # things, even that is not terribly stable.
        lines = file.getvalue().strip().split("\n")
        ndatasets = 10
        ntasks = 6
        nedges = 16
        nextra = 2  # graph header and closing
        self.assertEqual(len(lines), ndatasets + ntasks + nedges + nextra)

        # make sure that all node names are quoted
        nodeRe = re.compile(r"^([^ ]+) \[.+\];$")
        edgeRe = re.compile(r"^([^ ]+) *-> *([^ ]+);$")
        for line in lines:
            match = nodeRe.match(line)
            if match:
                node = match.group(1)
                self.assertEqual(node[0] + node[-1], '""')
                continue
            match = edgeRe.match(line)
            if match:
                for group in (1, 2):
                    node = match.group(group)
                    self.assertEqual(node[0] + node[-1], '""')
                continue

        # make sure components are connected appropriately
        self.assertIn('"D" -> "D.C";', file.getvalue())

        # make sure there is a connection created for metadata if someone
        # tries to read it in
        self.assertIn('"task3" -> "task3_metadata"', file.getvalue())


class MyMemoryTestCase(lsst.utils.tests.MemoryTestCase):
    pass


def setup_module(module):
    lsst.utils.tests.init()


if __name__ == "__main__":
    lsst.utils.tests.init()
    unittest.main()
