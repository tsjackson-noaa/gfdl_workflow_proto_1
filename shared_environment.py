import os
import sys
import glob
import shutil
import timeit
from abc import ABCMeta, abstractmethod
if os.name == 'posix' and sys.version_info[0] < 3:
    try:
        import subprocess32 as subprocess
    except (ImportError, ModuleNotFoundError):
        import subprocess
else:
    import subprocess
import util
from shared_diagnostic import Diagnostic

class EnvironmentManager(object):
    # analogue of TestSuite in xUnit - abstract base class
    __metaclass__ = ABCMeta

    def __init__(self, config, verbose=0):
        if 'pod_list' in config['case_list'][0]:
            # run a set of PODs specific to this model
            pod_list = config['case_list'][0]['pod_list']
        else:
            pod_list = config['pod_list'] # use global list of PODs
        self.pods = []
        for pod_name in pod_list: # list of pod names to do here
            try:
                pod = Diagnostic(pod_name)
            except AssertionError as error:  
                print str(error)
            if verbose > 0: print "POD long name: ", pod.long_name
            self.pods.append(pod)

    # -------------------------------------
    # following are specific details that must be implemented in child class 

    @abstractmethod
    def create_environment(self):
        pass 

    @abstractmethod
    def set_pod_env(self, pod):
        pass 

    @abstractmethod
    def activate_env_command(self, pod):
        pass 

    @abstractmethod
    def deactivate_env_command(self, pod):
        pass 

    @abstractmethod
    def destroy_environment(self):
        pass 

    # -------------------------------------

    def run(self, config, verbose=0):
        os.chdir(os.environ["WORKING_DIR"])

        for pod in self.pods:
            # Find and confirm POD driver script , program (Default = {pod_name,driver}.{program} options)
            # Each pod could have a settings files giving the name of its driver script and long name
            if verbose > 0: print("--- MDTF.py Starting POD "+pod.name+"\n")

            pod.setUp()
            # skip this pod if missing data
            if pod.missing_files != []:
                continue

            pod.logfile_obj = open(os.path.join(os.environ["WK_DIR"], pod.name+".log"), 'w')

            run_command = pod.run_command()          
            if config['envvars']['test_mode']:
                run_command = 'echo "TEST MODE: would call {}"'.format(run_command)
            commands = [
                self.activate_env_command(pod), pod.validate_command(), 
                run_command, self.deactivate_env_command(pod)
                ]
            # '&&' so we abort if any command in the sequence fails.
            commands = ' && '.join([s for s in commands if s])
 
            print("Calling :  "+run_command) # This is where the POD is called #
            print('Will run in env: '+pod.env)
            start_time = timeit.default_timer()
            try:
                # Need to run bash explicitly because 'conda activate' sources 
                # env vars (can't do that in posix sh). tcsh could also work.
                pod.process_obj = subprocess.Popen(
                    ['bash', '-c', commands],
                    env=os.environ, stdout=pod.logfile_obj, stderr=subprocess.STDOUT)
            except OSError as e:
                print('ERROR :',e.errno,e.strerror)
                print(" occured with call: " +run_command)

        # if this were python3 we'd have asyncio, instead wait for each process
        # to terminate and close all log files
        for pod in self.pods:
            if pod.process_obj is not None:
                pod.process_obj.wait()
                pod.process_obj = None
            if pod.logfile_obj is not None:
                pod.logfile_obj.close()
                pod.logfile_obj = None

    # -------------------------------------

    def tearDown(self):
        # call diag's tearDown to clean up
        for pod in self.pods:
            pod.tearDown()
        self.destroy_environment()


class UnmanagedEnvironment(EnvironmentManager):
    # Do not attempt to switch execution environments for each POD.
    def create_environment(self):
        pass 
    
    def destroy_environment(self):
        pass 

    def set_pod_env(self, pod):
        pass

    def activate_env_command(self, pod):
        return ''

    def deactivate_env_command(self, pod):
        return '' 


class CondaEnvironmentManager(EnvironmentManager):
    # Use Anaconda to switch execution environments.
    def create_environment(self):
        pass 

    def destroy_environment(self):
        pass 

    def set_pod_env(self, pod):
        keys = [s.lower() for s in pod.programs]
        if ('r' in keys) or ('rscript' in keys):
            pod.env = '_MDTF-diagnostics-R'
        elif 'ncl' in keys:
            pod.env = '_MDTF-diagnostics-NCL'
        else:
            pod.env = '_MDTF-diagnostics'

    def activate_env_command(self, pod):
        # Source conda_init.sh to set things that aren't set b/c we aren't 
        # in an interactive shell. 
        return 'source {}/src/conda_init.sh && conda activate {}'.format(
            os.environ['DIAG_HOME'], pod.env
            )

    def deactivate_env_command(self, pod):
        return '' 
