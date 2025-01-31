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

__all__ = ["DataIdMatch"]

import operator
from typing import Any, Callable, List, Optional, Tuple

import astropy.time
from lsst.daf.butler import DataId
from lsst.daf.butler.registry.queries.expressions import Node, ParserYacc, TreeVisitor  # type: ignore


class _DataIdMatchTreeVisitor(TreeVisitor):
    """Expression tree visitor which evaluates expression using values from
    DataId.
    """

    def __init__(self, dataId: DataId):
        self.dataId = dataId

    def visitNumericLiteral(self, value: str, node: Node) -> Any:
        # docstring is inherited from base class
        try:
            return int(value)
        except ValueError:
            return float(value)

    def visitStringLiteral(self, value: str, node: Node) -> Any:
        # docstring is inherited from base class
        return value

    def visitTimeLiteral(self, value: astropy.time.Time, node: Node) -> Any:
        # docstring is inherited from base class
        return value

    def visitRangeLiteral(self, start: int, stop: int, stride: Optional[int], node: Node) -> Any:
        # docstring is inherited from base class
        if stride is None:
            return range(start, stop + 1)
        else:
            return range(start, stop + 1, stride)

    def visitIdentifier(self, name: str, node: Node) -> Any:
        # docstring is inherited from base class
        return self.dataId[name]

    def visitUnaryOp(self, operator_name: str, operand: Any, node: Node) -> Any:
        # docstring is inherited from base class
        operators: dict[str, Callable[[Any], Any]] = {
            "NOT": operator.not_,
            "+": operator.pos,
            "-": operator.neg,
        }
        return operators[operator_name](operand)

    def visitBinaryOp(self, operator_name: str, lhs: Any, rhs: Any, node: Node) -> Any:
        # docstring is inherited from base class
        operators = {
            "OR": operator.or_,
            "AND": operator.and_,
            "+": operator.add,
            "-": operator.sub,
            "*": operator.mul,
            "/": operator.truediv,
            "%": operator.mod,
            "=": operator.eq,
            "!=": operator.ne,
            "<": operator.lt,
            ">": operator.gt,
            "<=": operator.le,
            ">=": operator.ge,
        }
        return operators[operator_name](lhs, rhs)

    def visitIsIn(self, lhs: Any, values: List[Any], not_in: bool, node: Node) -> Any:
        # docstring is inherited from base class
        is_in = True
        for value in values:
            if not isinstance(value, range):
                value = [value]
            if lhs in value:
                break
        else:
            is_in = False
        if not_in:
            is_in = not is_in
        return is_in

    def visitParens(self, expression: Any, node: Node) -> Any:
        # docstring is inherited from base class
        return expression

    def visitTupleNode(self, items: Tuple[Any, ...], node: Node) -> Any:
        # docstring is inherited from base class
        raise NotImplementedError()

    def visitFunctionCall(self, name: str, args: List[Any], node: Node) -> Any:
        # docstring is inherited from base class
        raise NotImplementedError()

    def visitPointNode(self, ra: Any, dec: Any, node: Node) -> Any:
        # docstring is inherited from base class
        raise NotImplementedError()


class DataIdMatch:
    """Class that can match DataId against the user-defined string expression.

    Parameters
    ----------
    expression : `str`
        User-defined expression, supports syntax defined by daf_butler
        expression parser. Maps identifiers in the expression to the values of
        DataId.
    """

    def __init__(self, expression: str):
        parser = ParserYacc()
        self.expression = expression
        self.tree = parser.parse(expression)

    def match(self, dataId: DataId) -> bool:
        """Matches DataId contents against the expression.

        Parameters
        ----------
        dataId : `DataId`
            DataId that is matched against an expression.

        Returns
        -------
        match : `bool`
            Result of expression evaluation.

        Raises
        ------
        KeyError
            Raised when identifier in expression is not defined for given
            `DataId`.
        TypeError
            Raised when expression evaluates to a non-boolean type or when
            operation in expression cannot be performed on operand types.
        NotImplementedError
            Raised when expression includes valid but unsupported syntax, e.g.
            function call.
        """
        visitor = _DataIdMatchTreeVisitor(dataId)
        result = self.tree.visit(visitor)
        if not isinstance(result, bool):
            raise TypeError(f"Expression '{self.expression}' returned non-boolean object {type(result)}")
        return result
