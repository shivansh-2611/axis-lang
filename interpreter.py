"""
AXIS Interpreter - Tree-Walking Interpreter for Script Mode
Executes AST directly without compilation
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable
from syntactic_analyzer import (
    Program, Function, Block, Statement, VarDecl, Assignment, Return,
    If, While, Break, Continue, Write, Expression, BinaryOp, UnaryOp,
    Literal, StringLiteral, Identifier, Call,
    Read, Readln, Readchar, ReadFailed
)


class BreakException(Exception):
    """Thrown when 'break' is encountered"""
    pass


class ContinueException(Exception):
    """Thrown when 'continue' is encountered"""
    pass


class ReturnException(Exception):
    """Thrown when 'give' (return) is encountered"""
    def __init__(self, value: Any):
        self.value = value


@dataclass
class InterpreterState:
    """Runtime state for the interpreter"""
    variables: Dict[str, Any]
    functions: Dict[str, Function]
    call_depth: int = 0
    max_call_depth: int = 1000
    read_failed: bool = False


class Interpreter:
    def __init__(self):
        self.state = InterpreterState(
            variables={},
            functions={},
        )
    
    def run(self, program: Program) -> int:
        """Execute a script-mode program, returns exit code"""
        if program.mode != "script":
            raise RuntimeError("Interpreter only handles script mode")
        
        # Register all functions
        for func in program.functions:
            self.state.functions[func.name] = func
        
        # Execute top-level statements
        try:
            for stmt in program.statements:
                self.execute_statement(stmt)
            return 0  # Success
        except ReturnException as e:
            # Top-level return with value
            if isinstance(e.value, int):
                return e.value
            return 0
    
    def execute_statement(self, stmt: Statement):
        """Execute a single statement"""
        if isinstance(stmt, VarDecl):
            self.execute_vardecl(stmt)
        elif isinstance(stmt, Assignment):
            self.execute_assignment(stmt)
        elif isinstance(stmt, Return):
            value = self.evaluate(stmt.value) if stmt.value else None
            raise ReturnException(value)
        elif isinstance(stmt, If):
            self.execute_if(stmt)
        elif isinstance(stmt, While):
            self.execute_while(stmt)
        elif isinstance(stmt, Break):
            raise BreakException()
        elif isinstance(stmt, Continue):
            raise ContinueException()
        elif isinstance(stmt, Write):
            self.execute_write(stmt)
        elif isinstance(stmt, Expression):
            # Expression statement (e.g., function call)
            self.evaluate(stmt)
        else:
            raise RuntimeError(f"Unknown statement type: {type(stmt).__name__}")
    
    def execute_vardecl(self, stmt: VarDecl):
        """Declare and optionally initialize a variable"""
        value = None
        if stmt.init:
            value = self.evaluate(stmt.init)
        self.state.variables[stmt.name] = value
    
    def execute_assignment(self, stmt: Assignment):
        """Assign a value to a variable"""
        if not isinstance(stmt.target, Identifier):
            raise RuntimeError("Assignment target must be an identifier")
        value = self.evaluate(stmt.value)
        name = stmt.target.name
        if name not in self.state.variables:
            raise RuntimeError(f"Undefined variable: {name}")
        self.state.variables[name] = value
    
    def execute_if(self, stmt: If):
        """Execute an if/when statement"""
        condition = self.evaluate(stmt.condition)
        if condition:
            self.execute_block(stmt.then_block)
        elif stmt.else_block:
            self.execute_block(stmt.else_block)
    
    def execute_while(self, stmt: While):
        """Execute a while/loop statement"""
        while True:
            # Check condition (for loop/repeat, condition is always True)
            condition = self.evaluate(stmt.condition)
            if not condition:
                break
            
            try:
                self.execute_block(stmt.body)
            except BreakException:
                break
            except ContinueException:
                continue
    
    def execute_block(self, block: Block):
        """Execute a block of statements"""
        for stmt in block.statements:
            self.execute_statement(stmt)
    
    def execute_write(self, stmt: Write):
        """Execute write/writeln"""
        value = self.evaluate(stmt.value)
        
        if isinstance(value, bool):
            output = "True" if value else "False"
        elif isinstance(value, str):
            output = value
        else:
            output = str(value)
        
        if stmt.newline:
            print(output)
        else:
            print(output, end='')
    
    def evaluate(self, expr: Expression) -> Any:
        """Evaluate an expression and return its value"""
        if isinstance(expr, Literal):
            # Literal has value and type fields
            if expr.type == 'bool':
                return expr.value == 'True' or expr.value == '1'
            else:
                # Integer literal
                return int(expr.value)
        
        elif isinstance(expr, StringLiteral):
            return expr.value
        
        elif isinstance(expr, Identifier):
            name = expr.name
            if name not in self.state.variables:
                raise RuntimeError(f"Undefined variable: {name}")
            return self.state.variables[name]
        
        elif isinstance(expr, BinaryOp):
            return self.evaluate_binary(expr)
        
        elif isinstance(expr, UnaryOp):
            return self.evaluate_unary(expr)
        
        elif isinstance(expr, Call):
            return self.evaluate_function_call(expr)
        
        elif isinstance(expr, Read):
            return self.evaluate_read()
        
        elif isinstance(expr, Readln):
            return self.evaluate_readln()
        
        elif isinstance(expr, Readchar):
            return self.evaluate_readchar()
        
        elif isinstance(expr, ReadFailed):
            return self.state.read_failed
        
        else:
            raise RuntimeError(f"Unknown expression type: {type(expr).__name__}")
    
    def evaluate_binary(self, expr: BinaryOp) -> Any:
        """Evaluate a binary operation"""
        left = self.evaluate(expr.left)
        right = self.evaluate(expr.right)
        op = expr.op
        
        # String concatenation
        if op == '+' and isinstance(left, str) and isinstance(right, str):
            return left + right
        
        # Numeric/boolean operations
        if op == '+':
            return left + right
        elif op == '-':
            return left - right
        elif op == '*':
            return left * right
        elif op == '/':
            if right == 0:
                raise RuntimeError("Division by zero")
            return left // right  # Integer division
        elif op == '%':
            if right == 0:
                raise RuntimeError("Modulo by zero")
            return left % right
        elif op == '&':
            return left & right
        elif op == '|':
            return left | right
        elif op == '^':
            return left ^ right
        elif op == '<<':
            return left << right
        elif op == '>>':
            return left >> right
        elif op == '==':
            return left == right
        elif op == '!=':
            return left != right
        elif op == '<':
            return left < right
        elif op == '<=':
            return left <= right
        elif op == '>':
            return left > right
        elif op == '>=':
            return left >= right
        else:
            raise RuntimeError(f"Unknown binary operator: {op}")
    
    def evaluate_unary(self, expr: UnaryOp) -> Any:
        """Evaluate a unary operation"""
        operand = self.evaluate(expr.operand)
        op = expr.op
        
        if op == '-':
            return -operand
        elif op == '!':
            return not operand
        else:
            raise RuntimeError(f"Unknown unary operator: {op}")
    
    def evaluate_function_call(self, expr: Call) -> Any:
        """Call a user-defined function"""
        name = expr.name
        
        if name not in self.state.functions:
            raise RuntimeError(f"Undefined function: {name}")
        
        # Check call depth
        if self.state.call_depth >= self.state.max_call_depth:
            raise RuntimeError("Stack overflow in script mode")
        
        func = self.state.functions[name]
        
        # For MVP: no parameter support yet
        if len(expr.args) > 0 or len(func.params) > 0:
            raise RuntimeError("Function parameters not yet supported in script mode")
        
        # Save current variables (simple scope)
        saved_vars = self.state.variables.copy()
        self.state.call_depth += 1
        
        try:
            self.execute_block(func.body)
            return None  # No return value
        except ReturnException as e:
            return e.value
        finally:
            self.state.variables = saved_vars
            self.state.call_depth -= 1
    
    def evaluate_read(self) -> str:
        """Read all input until EOF"""
        try:
            import sys
            content = sys.stdin.read()
            self.state.read_failed = len(content) == 0
            return content
        except Exception:
            self.state.read_failed = True
            return ""
    
    def evaluate_readln(self) -> str:
        """Read one line from stdin"""
        try:
            line = input()
            self.state.read_failed = False
            return line
        except EOFError:
            self.state.read_failed = True
            return ""
    
    def evaluate_readchar(self) -> int:
        """Read a single character, returns -1 on EOF"""
        try:
            import sys
            char = sys.stdin.read(1)
            if not char:
                self.state.read_failed = True
                return -1
            self.state.read_failed = False
            return ord(char)
        except Exception:
            self.state.read_failed = True
            return -1


def interpret(source: str) -> int:
    """Convenience function to interpret AXIS script source code"""
    from tokenization_engine import Lexer
    from syntactic_analyzer import Parser
    
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    
    parser = Parser(tokens)
    program = parser.parse()
    
    if program.mode != "script":
        raise RuntimeError("Source is not in script mode. Use 'mode script' at the top.")
    
    interpreter = Interpreter()
    return interpreter.run(program)


if __name__ == '__main__':
    # Quick test
    test_code = '''mode script

writeln("Hello from AXIS Script!")
x: i32 = 42
writeln(x)

when x > 10:
    writeln("x is big")
'''
    
    exit_code = interpret(test_code)
    print(f"\n[Exit code: {exit_code}]")
