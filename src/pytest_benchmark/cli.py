import argparse

import py

from pytest_benchmark.csv import CSVResults

from . import plugin
from .logger import Logger
from .plugin import add_csv_options
from .plugin import add_display_options
from .plugin import add_global_options
from .plugin import add_histogram_options
from .table import TableResults
from .utils import NAME_FORMATTERS
from .utils import first_or_value
from .utils import load_storage
from .utils import report_noprogress

COMPARE_HELP = '''examples:

    pytest-benchmark {0} 'Linux-CPython-3.5-64bit/*'

        Loads all benchmarks ran with that interpreter. Note the special quoting that disables your shell's glob
        expansion.

    pytest-benchmark {0} 0001

        Loads first run from all the interpreters.

    pytest-benchmark {0} /foo/bar/0001_abc.json /lorem/ipsum/0001_sir_dolor.json

        Loads runs from exactly those files.'''


class HelpAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        namespace.help = True
        namespace.command = values or 'help'


class CommandArgumentParser(argparse.ArgumentParser):
    commands = None
    commands_dispatch = None

    def __init__(self, *args, **kwargs):
        kwargs['add_help'] = False

        super(CommandArgumentParser, self).__init__(*args,
                                                    formatter_class=argparse.RawDescriptionHelpFormatter,
                                                    **kwargs)
        self.add_argument(
            '-h', '--help',
            metavar='COMMAND',
            nargs='?', action=HelpAction, help='Display help and exit.'
        )
        self.add_command(
            'help',
            description='Display help and exit.'
        ).add_argument(
            'command',
            nargs='?', action=HelpAction
        )

    def add_command(self, name, **opts):
        if self.commands is None:
            self.commands = self.add_subparsers(
                title='commands', dest='command', parser_class=argparse.ArgumentParser,
            )
            self.commands_dispatch = {}
        if 'description' in opts and 'help' not in opts:
            opts['help'] = opts['description']

        command = self.commands.add_parser(
            name, formatter_class=argparse.RawDescriptionHelpFormatter, **opts
        )
        self.commands_dispatch[name] = command
        return command

    def parse_args(self):
        args = super(CommandArgumentParser, self).parse_args()
        if args.help:
            if args.command:
                return super(CommandArgumentParser, self).parse_args([args.command, '--help'])
            else:
                self.print_help()
                self.exit()
        elif not args.command:
            self.error('the following arguments are required: COMMAND (choose from %s)' % ', '.join(
                map(repr, self.commands.choices)))
        return args


def add_glob_or_file(addoption):
    addoption(
        'glob_or_file',
        nargs='*', help='Glob or exact path for json files. If not specified all runs are loaded.'
    )


def make_parser():
    parser = CommandArgumentParser('py.test-benchmark', description="pytest_benchmark's management commands.")
    add_global_options(parser.add_argument, prefix="")

    parser.add_command('list', description='List saved runs.')

    compare_command = parser.add_command(
        'compare',
        description='Compare saved runs.',
        epilog='''examples:

    pytest-benchmark compare 'Linux-CPython-3.5-64bit/*'

        Loads all benchmarks ran with that interpreter. Note the special quoting that disables your shell's glob
        expansion.

    pytest-benchmark compare 0001

        Loads first run from all the interpreters.

    pytest-benchmark compare /foo/bar/0001_abc.json /lorem/ipsum/0001_sir_dolor.json

        Loads runs from exactly those files.''')
    add_display_options(compare_command.add_argument, prefix="")
    add_histogram_options(compare_command.add_argument, prefix="")
    add_glob_or_file(compare_command.add_argument)
    add_csv_options(compare_command.add_argument, prefix="")

    return parser


def load(storage, glob_or_file, group_by):
    conftest = py.path.local('conftest.py')
    if conftest.check():
        conftest = conftest.pyimport()
    else:
        conftest = None

    groups = getattr(conftest, 'pytest_benchmark_group_stats', plugin.pytest_benchmark_group_stats)(
        benchmarks=storage.load_benchmarks(*glob_or_file),
        group_by=group_by,
        config=None,
    )
    return groups


def main():
    parser = make_parser()
    args = parser.parse_args()
    logger = Logger(args.verbose)
    storage = load_storage(args.storage, logger=logger, netrc=args.netrc)

    if args.command == 'list':
        for file in storage.query():
            print(file)
    elif args.command == 'compare':
        results_table = TableResults(
            args.columns, args.sort, first_or_value(args.histogram, False), NAME_FORMATTERS[args.name], logger
        )
        groups = load(storage, args.glob_or_file, args.group_by)

        results_table.display(TerminalReporter(), groups, progress_reporter=report_noprogress)
        if args.csv:
            results_csv = CSVResults(args.columns, args.sort, logger)
            output_file, = args.csv

            results_csv.render(output_file, groups)
    elif args.command is None:
        parser.error("missing command (available commands: %s)" % ', '.join(map(repr, parser.commands.choices)))


class TerminalReporter(object):
    def __init__(self):
        self._tw = py.io.TerminalWriter()

    def ensure_newline(self):
        pass

    def write(self, content, **markup):
        self._tw.write(content, **markup)

    def write_line(self, line, **markup):
        if not py.builtin._istext(line):
            line = py.builtin.text(line, errors="replace")
        self._tw.line(line, **markup)

    def rewrite(self, line, **markup):
        line = str(line)
        self._tw.write("\r" + line, **markup)

    def write_sep(self, sep, title=None, **markup):
        self._tw.sep(sep, title, **markup)

    def section(self, title, sep="=", **kw):
        self._tw.sep(sep, title, **kw)

    def line(self, msg, **kw):
        self._tw.line(msg, **kw)
