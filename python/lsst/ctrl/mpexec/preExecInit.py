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

__all__ = ["PreExecInit"]

# -------------------------------
#  Imports of standard modules --
# -------------------------------
import logging
from typing import TYPE_CHECKING, Any, Iterable

# -----------------------------
#  Imports for other modules --
# -----------------------------
from lsst.daf.butler import DatasetType
from lsst.daf.butler.registry import ConflictingDefinitionError
from lsst.pipe.base import PipelineDatasetTypes
from lsst.utils.packages import Packages

from .mock_task import MockButlerQuantumContext

if TYPE_CHECKING:
    from lsst.daf.butler import Butler
    from lsst.pipe.base import QuantumGraph, TaskFactory

_LOG = logging.getLogger(__name__)


class PreExecInit:
    """Initialization of registry for QuantumGraph execution.

    This class encapsulates all necessary operations that have to be performed
    on butler and registry to prepare them for QuantumGraph execution.

    Parameters
    ----------
    butler : `~lsst.daf.butler.Butler`
        Data butler instance.
    taskFactory : `~lsst.pipe.base.TaskFactory`
        Task factory.
    extendRun : `bool`, optional
        If `True` then do not try to overwrite any datasets that might exist
        in ``butler.run``; instead compare them when appropriate/possible.  If
        `False`, then any existing conflicting dataset will cause a butler
        exception to be raised.
    mock : `bool`, optional
        If `True` then also do initialization needed for pipeline mocking.
    """

    def __init__(self, butler: Butler, taskFactory: TaskFactory, extendRun: bool = False, mock: bool = False):
        self.butler = butler
        self.taskFactory = taskFactory
        self.extendRun = extendRun
        self.mock = mock
        if self.extendRun and self.butler.run is None:
            raise RuntimeError(
                "Cannot perform extendRun logic unless butler is initialized "
                "with a default output RUN collection."
            )

    def initialize(
        self,
        graph: QuantumGraph,
        saveInitOutputs: bool = True,
        registerDatasetTypes: bool = False,
        saveVersions: bool = True,
    ) -> None:
        """Perform all initialization steps.

        Convenience method to execute all initialization steps. Instead of
        calling this method and providing all options it is also possible to
        call methods individually.

        Parameters
        ----------
        graph : `~lsst.pipe.base.QuantumGraph`
            Execution graph.
        saveInitOutputs : `bool`, optional
            If ``True`` (default) then save "init outputs", configurations,
            and package versions to butler.
        registerDatasetTypes : `bool`, optional
            If ``True`` then register dataset types in registry, otherwise
            they must be already registered.
        saveVersions : `bool`, optional
            If ``False`` then do not save package versions even if
            ``saveInitOutputs`` is set to ``True``.
        """
        # register dataset types or check consistency
        self.initializeDatasetTypes(graph, registerDatasetTypes)

        # Save task initialization data or check that saved data
        # is consistent with what tasks would save
        if saveInitOutputs:
            self.saveInitOutputs(graph)
            self.saveConfigs(graph)
            if saveVersions:
                self.savePackageVersions(graph)

    def initializeDatasetTypes(self, graph: QuantumGraph, registerDatasetTypes: bool = False) -> None:
        """Save or check DatasetTypes output by the tasks in a graph.

        Iterates over all DatasetTypes for all tasks in a graph and either
        tries to add them to registry or compares them to existing ones.

        Parameters
        ----------
        graph : `~lsst.pipe.base.QuantumGraph`
            Execution graph.
        registerDatasetTypes : `bool`, optional
            If ``True`` then register dataset types in registry, otherwise
            they must be already registered.

        Raises
        ------
        ValueError
            Raised if existing DatasetType is different from DatasetType
            in a graph.
        KeyError
            Raised if ``registerDatasetTypes`` is ``False`` and DatasetType
            does not exist in registry.
        """
        pipeline = graph.taskGraph
        pipelineDatasetTypes = PipelineDatasetTypes.fromPipeline(
            pipeline, registry=self.butler.registry, include_configs=True, include_packages=True
        )

        for datasetTypes, is_input in (
            (pipelineDatasetTypes.initIntermediates, True),
            (pipelineDatasetTypes.initOutputs, False),
            (pipelineDatasetTypes.intermediates, True),
            (pipelineDatasetTypes.outputs, False),
        ):
            self._register_output_dataset_types(registerDatasetTypes, datasetTypes, is_input)

        if self.mock:
            # register special mock data types, skip logs and metadata
            skipDatasetTypes = {taskDef.metadataDatasetName for taskDef in pipeline}
            skipDatasetTypes |= {taskDef.logOutputDatasetName for taskDef in pipeline}
            for datasetTypes, is_input in (
                (pipelineDatasetTypes.intermediates, True),
                (pipelineDatasetTypes.outputs, False),
            ):
                mockDatasetTypes = []
                for datasetType in datasetTypes:
                    if not (datasetType.name in skipDatasetTypes or datasetType.isComponent()):
                        mockDatasetTypes.append(
                            DatasetType(
                                MockButlerQuantumContext.mockDatasetTypeName(datasetType.name),
                                datasetType.dimensions,
                                "StructuredDataDict",
                            )
                        )
                if mockDatasetTypes:
                    self._register_output_dataset_types(registerDatasetTypes, mockDatasetTypes, is_input)

    def _register_output_dataset_types(
        self, registerDatasetTypes: bool, datasetTypes: Iterable[DatasetType], is_input: bool
    ) -> None:
        def _check_compatibility(datasetType: DatasetType, expected: DatasetType, is_input: bool) -> bool:
            # These are output dataset types so check for compatibility on put.
            is_compatible = expected.is_compatible_with(datasetType)

            if is_input:
                # This dataset type is also used for input so must be
                # compatible on get as ell.
                is_compatible = is_compatible and datasetType.is_compatible_with(expected)

            if is_compatible:
                _LOG.debug(
                    "The dataset type configurations differ (%s from task != %s from registry) "
                    "but the storage classes are compatible. Can continue.",
                    datasetType,
                    expected,
                )
            return is_compatible

        missing_datasetTypes = set()
        for datasetType in datasetTypes:
            # Only composites are registered, no components, and by this point
            # the composite should already exist.
            if registerDatasetTypes and not datasetType.isComponent():
                _LOG.debug("Registering DatasetType %s with registry", datasetType)
                # this is a no-op if it already exists and is consistent,
                # and it raises if it is inconsistent.
                try:
                    self.butler.registry.registerDatasetType(datasetType)
                except ConflictingDefinitionError:
                    if not _check_compatibility(
                        datasetType, self.butler.registry.getDatasetType(datasetType.name), is_input
                    ):
                        raise
            else:
                _LOG.debug("Checking DatasetType %s against registry", datasetType)
                try:
                    expected = self.butler.registry.getDatasetType(datasetType.name)
                except KeyError:
                    # Likely means that --register-dataset-types is forgotten.
                    missing_datasetTypes.add(datasetType.name)
                    continue
                if expected != datasetType:
                    if not _check_compatibility(datasetType, expected, is_input):
                        raise ValueError(
                            f"DatasetType configuration does not match Registry: {datasetType} != {expected}"
                        )

        if missing_datasetTypes:
            plural = "s" if len(missing_datasetTypes) != 1 else ""
            raise KeyError(
                f"Missing dataset type definition{plural}: {', '.join(missing_datasetTypes)}. "
                "Dataset types have to be registered with either `butler register-dataset-type` or "
                "passing `--register-dataset-types` option to `pipetask run`."
            )

    def saveInitOutputs(self, graph: QuantumGraph) -> None:
        """Write any datasets produced by initializing tasks in a graph.

        Parameters
        ----------
        graph : `~lsst.pipe.base.QuantumGraph`
            Execution graph.

        Raises
        ------
        TypeError
            Raised if ``extendRun`` is `True` but type of existing object in
            butler is different from new data.
        Exception
            Raised if ``extendRun`` is `False` and datasets already
            exists. Content of a butler collection may be changed if
            exception is raised.

        Notes
        -----
        If ``extendRun`` is `True` then existing datasets are not
        overwritten, instead we should check that their stored object is
        exactly the same as what we would save at this time. Comparing
        arbitrary types of object is, of course, non-trivial. Current
        implementation only checks the existence of the datasets and their
        types against the types of objects produced by tasks. Ideally we
        would like to check that object data is identical too but presently
        there is no generic way to compare objects. In the future we can
        potentially introduce some extensible mechanism for that.
        """
        _LOG.debug("Will save InitOutputs for all tasks")
        for taskDef in graph.iterTaskGraph():
            task = self.taskFactory.makeTask(
                taskDef.taskClass, taskDef.label, taskDef.config, None, self.butler
            )
            for name in taskDef.connections.initOutputs:
                attribute = getattr(taskDef.connections, name)
                initOutputVar = getattr(task, name)
                objFromStore = None
                if self.extendRun:
                    # check if it is there already
                    _LOG.debug(
                        "Retrieving InitOutputs for task=%s key=%s dsTypeName=%s", task, name, attribute.name
                    )
                    try:
                        objFromStore = self.butler.get(attribute.name, {}, collections=[self.butler.run])
                        # Types are supposed to be identical.
                        # TODO: Check that object contents is identical too.
                        if type(objFromStore) is not type(initOutputVar):
                            raise TypeError(
                                f"Stored initOutput object type {type(objFromStore)} "
                                f"is different  from task-generated type "
                                f"{type(initOutputVar)} for task {taskDef}"
                            )
                    except (LookupError, FileNotFoundError):
                        # FileNotFoundError likely means execution butler
                        # where refs do exist but datastore artifacts do not.
                        pass
                if objFromStore is None:
                    # butler will raise exception if dataset is already there
                    _LOG.debug("Saving InitOutputs for task=%s key=%s", taskDef.label, name)
                    self.butler.put(initOutputVar, attribute.name, {})

    def saveConfigs(self, graph: QuantumGraph) -> None:
        """Write configurations for pipeline tasks to butler or check that
        existing configurations are equal to the new ones.

        Parameters
        ----------
        graph : `~lsst.pipe.base.QuantumGraph`
            Execution graph.

        Raises
        ------
        TypeError
            Raised if ``extendRun`` is `True` but existing object in butler is
            different from new data.
        Exception
            Raised if ``extendRun`` is `False` and datasets already exists.
            Content of a butler collection should not be changed if exception
            is raised.
        """

        def logConfigMismatch(msg: str) -> None:
            """Log messages about configuration mismatch."""
            _LOG.fatal("Comparing configuration: %s", msg)

        _LOG.debug("Will save Configs for all tasks")
        # start transaction to rollback any changes on exceptions
        with self.butler.transaction():
            for taskDef in graph.taskGraph:
                configName = taskDef.configDatasetName

                oldConfig = None
                if self.extendRun:
                    try:
                        oldConfig = self.butler.get(configName, {}, collections=[self.butler.run])
                        if not taskDef.config.compare(oldConfig, shortcut=False, output=logConfigMismatch):
                            raise TypeError(
                                f"Config does not match existing task config {configName!r} in butler; "
                                "tasks configurations must be consistent within the same run collection"
                            )
                    except (LookupError, FileNotFoundError):
                        # FileNotFoundError likely means execution butler
                        # where refs do exist but datastore artifacts do not.
                        pass
                if oldConfig is None:
                    # butler will raise exception if dataset is already there
                    _LOG.debug("Saving Config for task=%s dataset type=%s", taskDef.label, configName)
                    self.butler.put(taskDef.config, configName, {})

    def savePackageVersions(self, graph: QuantumGraph) -> None:
        """Write versions of software packages to butler.

        Parameters
        ----------
        graph : `~lsst.pipe.base.QuantumGraph`
            Execution graph.

        Raises
        ------
        TypeError
            Raised if ``extendRun`` is `True` but existing object in butler is
            different from new data.
        """
        packages = Packages.fromSystem()
        _LOG.debug("want to save packages: %s", packages)
        datasetType = PipelineDatasetTypes.packagesDatasetName
        dataId: dict[str, Any] = {}
        oldPackages = None
        # start transaction to rollback any changes on exceptions
        with self.butler.transaction():
            if self.extendRun:
                try:
                    oldPackages = self.butler.get(datasetType, dataId, collections=[self.butler.run])
                    _LOG.debug("old packages: %s", oldPackages)
                except (LookupError, FileNotFoundError):
                    # FileNotFoundError likely means execution butler where
                    # refs do exist but datastore artifacts do not.
                    pass
            if oldPackages is not None:
                # Note that because we can only detect python modules that have
                # been imported, the stored list of products may be more or
                # less complete than what we have now.  What's important is
                # that the products that are in common have the same version.
                diff = packages.difference(oldPackages)
                if diff:
                    versions_str = "; ".join(f"{pkg}: {diff[pkg][1]} vs {diff[pkg][0]}" for pkg in diff)
                    raise TypeError(f"Package versions mismatch: ({versions_str})")
                else:
                    _LOG.debug("new packages are consistent with old")
                # Update the old set of packages in case we have more packages
                # that haven't been persisted.
                extra = packages.extra(oldPackages)
                if extra:
                    _LOG.debug("extra packages: %s", extra)
                    oldPackages.update(packages)
                    # have to remove existing dataset first, butler has no
                    # replace option.
                    ref = self.butler.registry.findDataset(datasetType, dataId, collections=[self.butler.run])
                    assert ref is not None, "Expecting to get dataset ref which is not None."
                    self.butler.pruneDatasets([ref], unstore=True, purge=True)
                    self.butler.put(oldPackages, datasetType, dataId)
            else:
                self.butler.put(packages, datasetType, dataId)
