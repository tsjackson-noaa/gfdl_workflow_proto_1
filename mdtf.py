#!/usr/bin/env python

# ======================================================================
# NOAA Model Diagnotics Task Force (MDTF) Diagnostic Driver
#
# March 2019
# Dani Coleman, NCAR
# Chih-Chieh (Jack) Chen, NCAR, 
# Yi-Hung Kuo, UCLA
#
# ======================================================================
# Usage
#
# USAGE: python mdtf.py input_file (default=namelist)
# The input file sets all model case/dates and which modules to run
# This file (mdtf.py) should NOT be modified
#
# Please see Getting Started [link] and Developer's Walk-Through
# for full description of how to run
# ======================================================================
# What's Included
#
# The input file (namelist) provided in the distribution will run
# the following diagnostic modules (PODs) by default:
#    Convective Transition Diagnostics   from J. David Neelin (UCLA)
#    MJO Teleconnections                 from Eric Maloney (CSU)
#    Extratropical Variance (EOF 500hPa) from CESM/AMWG (NCAR)
#    Wavenumber-Frequency Spectra        from CESM/AMWG (NCAR)
#    MJO Spectra and Phasing             from CESM/AMWG (NCAR)
#
# In addition, the following package is provided in full but does not run
# by default because of higher memory requirements
#    Diurnal Cycle of Precipitation      from Rich Neale (NCAR)
#
# The following modules are under development. Future releases will be
# available on the  MDTF main page
# http://www.cesm.ucar.edu/working_groups/Atmosphere/mdtf-diagnostics-package/index.html
#    MJO Propagation and Amplitude        from Xianan Jiang, UCLA
#    ENSO Moist Static Energy budget      from Hariharasubramanian Annamalai, U. Hawaii
#    Warm Rain Microphysics               from Kentaroh Suzuki (AORI, U. Tokyo
#    AMOC 3D structure                    from Xiaobiao Xu (FSU/COAPS)
#
# The MDTF code package and the participating PODs are distributed under
# the LGPLv3 license (see LICENSE.txt).
# ======================================================================
# Requirements
#
# As well as Ncar Command Language (NCL),
# this release uses the following Python modules: 
#     os, glob, json, dataset, numpy, scipy, matplotlib, 
#     networkx, warnings, numba, netcdf4
# ======================================================================

import os
import sys
import argparse
from ConfigParser import _Chainmap as ChainMap # in collections in py3
import util
import data_manager
import environment_manager
from shared_diagnostic import Diagnostic
try:
    import gfdl
except ImportError:
    pass  

def argparse_wrapper():
    """Wraps command-line arguments to script.

    Returns: :obj:`dict` of command-line parameters.
    """
    cwd = os.path.dirname(os.path.realpath(__file__)) # gets dir of currently executing script
    code_root = os.path.realpath(os.path.join(cwd, '..')) # parent dir of that
    parser = argparse.ArgumentParser(
        epilog="All command-line arguments override defaults set in src/config.yml."
    )
    parser.add_argument("-v", "--verbosity", 
        action="count",
        help="Increase output verbosity")
    parser.add_argument("--frepp", 
        action="store_true", # so default to False
        help="Set flag to take configuration info from env vars set by frepp.")
    # default paths set in config.yml/paths
    parser.add_argument('--CODE_ROOT', 
        nargs='?', default=code_root,
        help="Code installation directory.")
    parser.add_argument('--MODEL_DATA_ROOT', 
        nargs='?',
        help="Parent directory containing results from different models.")
    parser.add_argument('--OBS_DATA_ROOT', 
        nargs='?', 
        help="Parent directory containing observational data used by individual PODs.")
    parser.add_argument('--WORKING_DIR', 
        nargs='?',
        help="Working directory.")
    parser.add_argument('--OUTPUT_DIR', 
        nargs='?',
        help="Directory to write output files. Defaults to working directory.")
    # defaults set in config.yml/settings
    parser.add_argument("--test_mode", 
        action="store_true", # so default to False
        help="Set flag to do a dry run, disabling calls to PODs")
    parser.add_argument("--save_nc", 
        action="store_true", # so default to False
        help="Set flag to have PODs save netCDF files of processed data.")
    parser.add_argument('--data_manager', 
        nargs='?',
        help="Method to fetch model data. Currently supported options are {'Localfile'}.")
    parser.add_argument('--environment_manager', 
        nargs='?',
        help="Method to manage POD runtime dependencies. Currently supported options are {'None', 'Conda'}.")                                      
    # casename args, set by frepp
    parser.add_argument('--CASENAME', 
        nargs='?')
    parser.add_argument('--model', 
        nargs='?')
    parser.add_argument('--experiment', 
        nargs='?')
    parser.add_argument('--CASE_ROOT_DIR', 
        nargs='?')
    parser.add_argument('--FIRSTYR', 
        nargs='?', type=int)
    parser.add_argument('--LASTYR', 
        nargs='?', type=int)
    parser.add_argument("--ignore-component", 
        action="store_true", # so default to False
        help="Set flag to ignore model component passed by frepp and search entire /pp/ directory.")
    parser.add_argument("--component", 
        nargs='?')
    parser.add_argument("--data_freq", 
        nargs='?')   
    parser.add_argument("--chunk_freq", 
        nargs='?')       
    parser.add_argument('--config_file', 
        nargs='?', default=os.path.join(cwd, 'config.yml'),
        help="Configuration file.")
    args = parser.parse_args()
    
    d = args.__dict__
    if args.verbosity == None:
        d['verbose'] = 1
    else:
        d['verbose'] = args.verbosity + 1 # fix for case  verb = 0
    # remove entries that weren't set
    del_keys = [key for key in d if d[key] is None]
    for key in del_keys:
        del d[key]
    return d

def caselist_from_args(args):
    d = {}
    for k in ['CASENAME', 'FIRSTYR', 'LASTYR', 'root_dir', 'component', 
        'chunk_freq', 'data_freq', 'model', 'experiment', 'variable_convention']:
        if k in args:
            d[k] = args[k]
    for k in ['model', 'variable_convention']:
        if k not in d:
            d[k] = 'CMIP_GFDL'
    if 'CASENAME' not in d:
        d['CASENAME'] = '{}_{}'.format(d['model'], d['experiment'])
    if 'root_dir' not in d and 'CASE_ROOT_DIR' in args:
        d['root_dir'] = args['CASE_ROOT_DIR']
    return [d]

def parse_mdtf_args(user_args_list, default_args, rel_paths_root=''):
    """Parse script options.

    We provide three ways to configure the script. In order of precendence,
    they are:

    1. Parameter substitution via GFDL's internal `frepp` utility; see
       `https://wiki.gfdl.noaa.gov/index.php/FRE_User_Documentation`_.

    2. Through command-line arguments.

    3. Through default values set in a YAML configuration file, by default
       in src/config.yml.

    This function applies the precendence and returns a single dict of the
    actual configuration.

    Args:

    Returns: :obj:`dict` of configuration settings.
    """
    if isinstance(user_args_list, dict):
        user_args = user_args_list
    elif isinstance(user_args_list, list):
        user_args = ChainMap(*user_args_list)
    else:
        user_args = dict()
    # overwrite defaults with command-line args.
    for section in ['paths', 'settings']:
        for key in default_args[section]:
            if key in user_args:
                default_args[section][key] = user_args[key]
    if ('model' in user_args and 'experiment' in user_args) or \
        'CASENAME' in user_args:
        # also set up caselist with frepp data
        default_args['case_list'] = caselist_from_args(user_args)

    if 'CODE_ROOT' in user_args:
        # only let this be overridden if we're in a unit test
        rel_paths_root = user_args['CODE_ROOT']
    # convert relative to absolute paths
    for key, val in default_args['paths'].items():
        default_args['paths'][key] = util.resolve_path(val, rel_paths_root)

    return default_args

def set_mdtf_env_vars(config, verbose=0):
    # pylint: disable=maybe-no-member
    paths = util.PathManager()
    util.check_required_dirs(
        already_exist = [paths.CODE_ROOT, paths.MODEL_DATA_ROOT, paths.OBS_DATA_ROOT], 
        create_if_nec = [paths.WORKING_DIR, paths.OUTPUT_DIR], 
        verbose=verbose
        )

    config["envvars"] = config['settings'].copy()
    config["envvars"].update(config['paths'])
    # following are redundant but used by PODs
    config["envvars"]["RGB"] = paths.CODE_ROOT+"/src/rgb"

def manual_dispatch(class_name):
    for mod in [data_manager, environment_manager, gfdl]:
        try:
            return getattr(mod, class_name)
        except:
            continue
    print "No class named {}.".format(class_name)
    raise Exception('no_class')

def main():
    print "==== Starting "+__file__

    cmdline_args = argparse_wrapper()
    print cmdline_args
    default_args = util.read_yaml(cmdline_args['config_file'])
    config = parse_mdtf_args(cmdline_args, default_args)
    print config #debug
    
    verbose = config['settings']['verbose']
    util.PathManager(config['paths']) # initialize
    set_mdtf_env_vars(config, verbose)
    DataMgr = manual_dispatch(
        config['settings']['data_manager'].title()+'DataManager'
    )
    EnvironmentMgr = manual_dispatch(
        config['settings']['environment_manager'].title()+'EnvironmentManager'
    )

    caselist = []
    # only run first case in list until dependence on env vars cleaned up
    for case_dict in config['case_list'][0:1]: 
        case = DataMgr(case_dict, config)
        for pod_name in case.pod_list:
            try:
                pod = Diagnostic(pod_name)
            except AssertionError as error:  
                print str(error)
            if verbose > 0: print "POD long name: ", pod.long_name
            case.pods.append(pod)
        case.setUp()
        case.fetch_data()
        caselist.append(case)

    for case in caselist:
        env = EnvironmentMgr(config)
        env.pods = case.pods # best way to do this?
        env.setUp()
        env.run()
        env.tearDown()

    for case in caselist:
        case.tearDown(config)

    print "Exiting normally from ",__file__


if __name__ == '__main__':
    main()