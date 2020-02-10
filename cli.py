from __future__ import print_function
import os
import sys
import argparse
from ConfigParser import _Chainmap as ChainMap # in collections in py3
import shlex
import collections
import util

class SingleMetavarHelpFormatter(argparse.ArgumentDefaultsHelpFormatter):
    """Modify help text formatter to only display variable placeholder 
    ("metavar") once, to save space. 
    Taken from https://stackoverflow.com/a/16969505
    """
    def __init__(self, *args, **kwargs):
        # tweak indentation of help strings
        if not kwargs.get('indent_increment', None):
            kwargs['indent_increment'] = 2
        if not kwargs.get('max_help_position', None):
            kwargs['max_help_position'] = 10
        super(SingleMetavarHelpFormatter, self).__init__(*args, **kwargs)

    def _format_action_invocation(self, action):
        if not action.option_strings:
            metavar, = self._metavar_formatter(action, action.dest)(1)
            return metavar
        else:
            parts = []
            if action.nargs == 0:
                # if the Optional doesn't take a value, format is: "-s, --long"
                parts.extend(action.option_strings)
            else:
                # if the Optional takes a value, format is: "-s ARGS, --long ARGS"
                default = action.dest.upper()
                args_string = self._format_args(action, default)
                ## NEW CODE:
                if args_string[0].isalpha():
                    args_string = '<' + args_string + '>'
                parts.extend(action.option_strings)
                parts[-1] += ' %s' % args_string
            return ', '.join(parts)

class ConfigManager(util.Singleton):
    def __init__(self, defaults_filename=None):
        # get dir of currently executing script: 
        cwd = os.path.dirname(os.path.realpath(__file__)) 
        self.code_root = os.path.dirname(cwd) # parent dir of that
        defaults_path = os.path.join(cwd, defaults_filename)

        # poor man's subparser: argparse's subparser doesn't handle this
        # use case easily, so just dispatch on first argument
        if len(sys.argv) == 1 or \
            len(sys.argv) == 2 and sys.argv[1].lower() == 'help':
            help_and_exit = True # print help and exit
        elif sys.argv[1].lower() == 'info': 
            # "subparser" for command-line info
            _CLIInfoHandler(self.code_root, sys.argv[2:])
            exit()
        else:
            help_and_exit = False
        # continue to set up default CLI from defaults.json file
        defaults = util.read_json(defaults_path)
        self.case_list = defaults.pop('case_list', [])
        self.pod_list = defaults.pop('pod_list', [])

        self.config = dict()
        self.parser_groups = dict()
        # no way to get this from public interface? _actions of group
        # contains all actions for entire parser
        self.parser_args_from_group = collections.defaultdict(list)
        defaults = self._init_default_parser(defaults, defaults_path)
        self.parser = self.make_parser(defaults)
        if help_and_exit:
            self.parser.print_help()
            exit()

    def iter_actions(self):
        for arg_list in self.parser_args_from_group:
            for arg in arg_list:
                yield arg

    @staticmethod
    def _append_to_entry(d, key, str_):
        if key in d:
            d[key] = d[key] + '\n' + str_
        else:
            d[key] = str_

    def _init_default_parser(self, d, config_path):
        # add more standard options to default parser
        d['formatter_class'] = SingleMetavarHelpFormatter
        if 'usage' not in d:
            d['usage'] = ("%(prog)s [options] CASE_ROOT_DIR\n"
                "{}%(prog)s info [INFO_TOPIC]").format(len('usage: ')*' ')
        self._append_to_entry(d, 'description',
            ("The second form ('mdtf info') prints information about available "
                "diagnostics."))
        d['arguments'] = util.coerce_to_iter(d.get('arguments', None), list)
        d['arguments'].extend([{
                "name": "root_dir",
                "is_positional": True,
                "nargs" : "?", # 0 or 1 occurences: might have set this with CASE_ROOT_DIR
                "help": "Root directory of model data to analyze.",
                "metavar" : "CASE_ROOT_DIR"
            },{
                'name':'version', 
                'action':'version', 'version':'%(prog)s 2.2'
            },{
                'name': 'config_file',
                'short_name': 'f',
                'help': """
                Path to a user configuration file. This can be a JSON
                file (a simple list of key:value pairs, or a modified copy of 
                the defaults file), or a text file containing command-line flags.
                Other options set via the command line will still override 
                settings in this file.
                """,
                'metavar': 'FILE'
            }])
        self._append_to_entry(d, 'epilog',
            "The default values above are set in {}.".format(config_path)
        )
        return d

    def make_parser(self, d):
        args = d.pop('arguments', None)
        arg_groups = d.pop('argument_groups', None)
        p_kwargs = util.filter_kwargs(d, argparse.ArgumentParser.__init__)
        p = argparse.ArgumentParser(**p_kwargs)
        for arg in args:
            # add arguments not in any group
            self.add_parser_argument(arg, p, 'parser')
        p._positionals.title = None
        p._optionals.title = 'GENERAL OPTIONS'
        for group in arg_groups:
            # add groups and arguments therein
            self.add_parser_group(group, p)
        return p

    def add_parser_group(self, d, target_obj):
        gp_nm = d.pop('name')
        if 'title' not in d:
            d['title'] = gp_nm
        args = d.pop('arguments', None)
        gp_kwargs = util.filter_kwargs(d, argparse._ArgumentGroup.__init__)
        gp_obj = target_obj.add_argument_group(**gp_kwargs)
        self.parser_groups[gp_nm] = gp_obj
        for arg in args:
            self.add_parser_argument(arg, gp_obj, gp_nm)
    
    @staticmethod
    def canonical_arg_name(str_):
        # convert flag or other specification to destination variable name
        # canonical identifier/destination always has _s, no -s (PEP8)
        return str_.lstrip('-').rstrip().replace('-', '_')

    def add_parser_argument(self, d, target_obj, target_name):
        # set flags:
        arg_nm = self.canonical_arg_name(d.pop('name'))
        assert arg_nm, "No argument name found in {}".format(d)
        arg_flags = [arg_nm]
        if d.pop('is_positional', False):
            # code to handle positional arguments
            pass
        else:
            # argument is a command-line flag (default)
            if 'dest' not in d:
                d['dest'] = arg_nm
            if '_' in arg_nm:
                # recognize both --hyphen_opt and --hyphen-opt (GNU CLI convention)
                arg_flags = [arg_nm.replace('_', '-'), arg_nm]
            arg_flags = ['--'+s for s in arg_flags]
            if 'short_name' in d:
                # recognize both --option and -O, if short_name defined
                arg_flags.append('-' + d.pop('short_name'))

        # type conversion of default value
        if 'type' in d:
            d['type'] = eval(d['type'])
            if 'default' in d:
                d['default'] = d['type'](d['default'])
        if d.get('action', '') == 'count' and 'default' in d:
            d['default'] = int(d['default'])
        # if d.pop('eval_default', False) and 'default' in d:
        #     d['default'] = eval(d['default'], XXX)

        # set more technical argparse options based on default value
        if 'default' in d:
            if isinstance(d['default'], basestring) and 'nargs' not in d:
                # unless explicitly specified, 
                # string-valued options accept 1 argument
                d['nargs'] = 1
            elif isinstance(d['default'], bool) and 'action' not in d:
                if d['default']:
                    d['action'] = 'store_false' # default true, false if flag set
                else:
                    d['action'] = 'store_true' # default false, true if flag set

        # change help string based on default value
        if d.pop('hidden', False):
            # do not list argument in "mdtf --help", but recognize it
            d['help'] = argparse.SUPPRESS
        elif 'default' in d:
            # display default value in help string
            #self._append_to_entry(d, 'help', "(default: %(default)s)")
            pass

        # d = util.filter_kwargs(d, argparse.ArgumentParser.add_argument)
        self.parser_args_from_group[target_name].append(
            target_obj.add_argument(*arg_flags, **d)
        )

    # def edit_argument(self, arg_nm, **kwargs):
    #     # change aspects of arguments after they're defined.
    #     action = self.parser_args[arg_nm]
    #     for k,v in kwargs.iteritems():
    #         if not hasattr(action, k):
    #             print("Warning: didn't find attribute {} for argument {}".format(k, arg_nm))
    #             continue
    #         setattr(action, k, v)

    def edit_defaults(self, **kwargs):
        # Change default value of arguments. If a key doesn't correspond to an
        # argument previously added, its value is still returned when parse_args()
        # is called.
        self.parser.set_defaults(**kwargs)
        
    def parse_cli(self):
        # explicitly set cmd-line options, parsed according to default parser
        cli_opts = vars(self.parser.parse_args())
        # default values only, from running default parser on empty input
        defaults = vars(self.parser.parse_args([]))

        # deal with options set in user-specified file, if present
        config_path = cli_opts.get('config_file', None)
        file_str = ''
        file_opts = dict()
        if config_path:
            try:
                with open(config_path, 'r') as f:
                    file_str = f.read()
            except Exception:
                print("ERROR: Can't read config file at {}.".format(config_path))
        if file_str:
            try:
                file_opts = util.parse_json(file_str)
                # overwrite default case_list and pod_list, if given
                if 'case_list' in file_opts:
                    self.case_list = file_opts.pop('case_list')
                if 'pod_list' in file_opts:
                    self.pod_list = file_opts.pop('pod_list')
                if 'argument_groups' in file_opts or 'arguments' in file_opts:
                    # assume config_file is a modified copy of the defaults,
                    # with options to define parser. Set up the parser and run 
                    # CLI arguments through it (instead of default).
                    custom_parser = self.make_parser(file_opts)
                    cli_opts = vars(custom_parser.parse_args())
                    # defaults set in config_file's parser
                    file_opts = vars(custom_parser.parse_args([]))
                else:
                    # assume config_file a JSON dict of option:value pairs.
                    file_opts = {
                        self.canonical_arg_name(k): v for k,v in file_opts.iteritems()
                    }
            except Exception:
                if 'json' in os.path.splitext('config_path')[1].lower():
                    print("ERROR: Couldn't parse JSON in {}.".format(config_path))
                    raise
                # assume config_file is a plain text file containing flags, etc.
                # as they would be passed on the command line.
                file_str = util.strip_comments(file_str, '#')
                file_opts = vars(self.parser.parse_args(shlex.split(file_str)))

        # CLI opts override options set from file, which override defaults
        self.config = dict(ChainMap(cli_opts, file_opts, defaults))


class _CLIInfoHandler(object):
    _pod_dir = 'diagnostics'
    _settings = 'settings.json'

    def __init__(self, code_root, arg_list):
        self.code_root = code_root
        self.pods = get_pod_list(code_root)
        self.cmds = ['diagnostics', 'PODs'] + self.pods
        if not arg_list:
            self.info_cmds()
        elif arg_list[0] in ['diagnostics', 'PODs']:
            self.info_diagnostics_all()
        elif arg_list[0] in self.pods:
            self.info_diagnostic(arg_list[0])
        else:
            print("ERROR: '{}' not a recognized diagnostic.".format(' '.join(arg_list)))
            self.info_cmds()
        # return to ConfigManager for program exit

    def info_cmds(self):
        print('Recognized topics for `mdtf.py info`:')
        print(', '.join(self.cmds))

    def info_diagnostics_all(self):
        print('List of installed diagnostics:')
        print(('Do `mdtf info <diagnostic>` for more info on a specific diagnostic '
            'or check documentation at github.com/NOAA-GFDL/MDTF-diagnostics.'))
        for pod in self.pods:
            try:
                d = util.read_json(
                    os.path.join(self.code_root, self._pod_dir, pod, self._settings)
                )
            except Exception:
                continue
            print('  {}: {}.'.format(pod, d['settings']['long_name']))

    def info_diagnostic(self, pod):
        d = util.read_json(
            os.path.join(self.code_root, self._pod_dir, pod, self._settings)
        )
        print('{}: {}.'.format(pod, d['settings']['long_name']))
        print(d['settings']['description'])
        print('Variables:')
        for var in d['varlist']:
            print('  {} ({}) @ {} frequency'.format(
                var['var_name'].replace('_var',''), 
                var.get('requirement',''), 
                var['freq'] 
            ))
            if 'alternates' in var:
                print ('    Alternates: {}'.format(
                    ', '.join([s.replace('_var','') for s in var['alternates']])
                ))

