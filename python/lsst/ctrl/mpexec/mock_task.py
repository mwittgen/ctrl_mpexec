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

import logging
from typing import Any, List, Union

from lsst.daf.butler import Butler, DatasetRef, Quantum
from lsst.pipe.base import (
    ButlerQuantumContext,
    DeferredDatasetRef,
    InputQuantizedConnection,
    OutputQuantizedConnection,
    PipelineTask,
    PipelineTaskConfig,
)
from lsst.utils.introspection import get_full_type_name


_LOG = logging.getLogger(__name__)


class MockButlerQuantumContext(ButlerQuantumContext):
    """Implementation of ButlerQuantumContext to use with a mock task.

    Parameters
    ----------
    butler : `~lsst.daf.butler.Butler`
        Data butler instance.
    quantum : `~lsst.daf.butler.Quantum`
        Execution quantum.

    Notes
    -----
    This implementation overrides get method to try to retrieve dataset from a
    mock dataset type if it exists. Get method always returns a dictionary.
    Put method stores the data with a mock dataset type, but also registers
    DatasetRef with registry using original dataset type.
    """

    def __init__(self, butler: Butler, quantum: Quantum):
        super().__init__(butler, quantum)
        self.butler = butler

    @classmethod
    def mockDatasetTypeName(cls, datasetTypeName: str) -> str:
        """Make mock dataset type name from actual dataset type name."""
        return "_mock_" + datasetTypeName

    def _get(self, ref: DatasetRef) -> Any:
        # docstring is inherited from the base class
        if isinstance(ref, DeferredDatasetRef):
            ref = ref.datasetRef
        datasetType = ref.datasetType

        typeName, component = datasetType.nameAndComponent()
        if component is not None:
            mockDatasetTypeName = self.mockDatasetTypeName(typeName)
        else:
            mockDatasetTypeName = self.mockDatasetTypeName(datasetType.name)

        try:
            mockDatasetType = self.butler.registry.getDatasetType(mockDatasetTypeName)
            ref = DatasetRef(mockDatasetType, ref.dataId)
            data = self.butler.get(ref)
        except KeyError:
            data = super()._get(ref)

        if not isinstance(data, dict):
            data = {
                "ref": {
                    "dataId": {key.name: ref.dataId[key] for key in ref.dataId.keys()},
                    "datasetType": ref.datasetType.name,
                },
                "type": get_full_type_name(type(data)),
            }
        if component is not None:
            data.update(component=component)
        return data

    def _put(self, value: Any, ref: DatasetRef):
        # docstring is inherited from the base class

        mockDatasetType = self.registry.getDatasetType(self.mockDatasetTypeName(ref.datasetType.name))
        mockRef = DatasetRef(mockDatasetType, ref.dataId)
        value.setdefault("ref", {}).update(datasetType=mockDatasetType.name)
        self.butler.put(value, mockRef)

        # also "store" non-mock refs
        self.registry._importDatasets([ref])

    def _checkMembership(self, ref: Union[List[DatasetRef], DatasetRef], inout: set):
        # docstring is inherited from the base class
        return


class MockPipelineTask(PipelineTask):
    """Implementation of PipelineTask used for running a mock pipeline.

    Notes
    -----
    This class overrides `runQuantum` to read all input datasetRefs and to
    store simple dictionary as output data. Output dictionary contains some
    provenance data about inputs, the task that produced it, and corresponding
    quantum. This class depends on `MockButlerQuantumContext` which knows how
    to store the output dictionary data with special dataset types.
    """

    ConfigClass = PipelineTaskConfig

    def runQuantum(
        self,
        butlerQC: ButlerQuantumContext,
        inputRefs: InputQuantizedConnection,
        outputRefs: OutputQuantizedConnection,
    ):
        # docstring is inherited from the base class
        quantum = butlerQC.quantum

        _LOG.info("Mocking execution of task '%s' on quantum %s", self.getName(), quantum.dataId)

        # read all inputs
        inputs = butlerQC.get(inputRefs)

        _LOG.info("Read input data for task '%s' on quantum %s", self.getName(), quantum.dataId)

        # To avoid very deep provenance we trim inputs to a single level
        for name, data in inputs.items():
            if isinstance(data, dict):
                data = [data]
            if isinstance(data, list):
                for item in data:
                    qdata = item.get("quantum", {})
                    qdata.pop("inputs", None)

        # store mock outputs
        for name, refs in outputRefs:
            if not isinstance(refs, list):
                refs = [refs]
            for ref in refs:
                data = {
                    "ref": {
                        "dataId": {key.name: ref.dataId[key] for key in ref.dataId.keys()},
                        "datasetType": ref.datasetType.name,
                    },
                    "quantum": {
                        "task": self.getName(),
                        "dataId": {key.name: quantum.dataId[key] for key in quantum.dataId.keys()},
                        "inputs": inputs,
                    },
                    "outputName": name,
                }
                butlerQC.put(data, ref)

        _LOG.info("Finished mocking task '%s' on quantum %s", self.getName(), quantum.dataId)
