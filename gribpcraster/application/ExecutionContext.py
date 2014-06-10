import getopt
import untangle
import collections
import os

from gribpcraster.exc.ApplicationException import ApplicationException
import util.date.Dates as Du
from util.logger.Logger import Logger
import util.file.FileManager as Fm
import util.conversion.FromStringConversion as Fsc
import time

#global_out_log_dir = './logs/'
PARAMETERS_XML = 'configuration/parameters.xml'
# KNOWN_INTERP_MODES = {'nearest': [],
#                       'invdist': [],
#                       'grib_invdist': [],
#                       'grib_nearest': []}
DEFAULT_VALUES = {'interpolation.mode': 'grib_nearest',
                  'outMaps.unitTime': '24'}


class ExecutionContext:
    def __init__(self, argv):

        self._inputArguments = {}
        self._showHelp = False
        self._addGeopotential = False
        self._params = {'outMaps.outDir': './', 'aggregation.forceZeroArray': False}

        try:
            #read cli input args (commands file path, input files, output dir, or shows help and exit)
            self._define_input_args(argv)
            if not (self.user_wants_to_add_geopotential() or self.user_wants_help() or self.user_wants_to_test()):
                #read config files and define execuition parameters (set defaults also)
                self._define_exec_params()
        except ApplicationException, err:
            raise err
        except ValueError, err:
            raise ApplicationException(err, None, str(err))
        except Exception, err:
            raise ApplicationException(err, None, str(err))

        #check numbers, existing dirs and files, supported options, semantics etc.
        try:
            #pass
            self._check_exec_params()
        except ApplicationException, err:
            raise err
        except ValueError, err:
            raise ApplicationException(err, None, str(err))
            #raise err
        except Exception, exc:
            raise ApplicationException(exc, None, str(exc))
            #raise exc

    def interpolate_with_grib(self):
        return self._params['interpolation.mode'].startswith('grib_')  # in ['grib_invdist', 'grib_nearest']

    def _log(self, message, level='DEBUG'):
        self._logger.log(message, level)

    def _define_input_args(self, argv):

        try:
            opts, argv = getopt.getopt(argv, "hc:o:i:I:m:T:l:d:g:t:s:e:f:x:", ['help', 'commandsFile=','outDir=','inputFile=',
                                                                         'inputFile2=','perturbationNumber=','dataTime='
                                                                         'loggerlLevel=', 'outLogDir=',
                                                                         'addGeopotential=', 'test=', 'start=', 'end=',
                                                                         'fmap=', 'ext='])
        except getopt.GetoptError, err:
            raise ApplicationException(err, None, str(err))

        self._params['input.two_resolution'] = False
        self._params['logger.level'] = 'INFO'
        self._params['logger.dir'] = './logs/'
        self._params['parameter.tstart'] = None
        self._params['parameter.tend'] = None
        self._params['parameter.dataTime'] = None
        self._params['outMaps.fmap'] = None
        self._params['outMaps.ext'] = None

        for opt, val in opts:
            if opt in ('-c', '--commandsFile'):
                self._inputArguments['commandsFile'] = val
            elif opt in ('-i', '--inputFile'):
                self._params['input.file'] = val
            elif opt in ('-s', '--start'):
                self._params['parameter.tstart'] = val
            elif opt in ('-e', '--end'):
                self._params['parameter.tend'] = val
            elif opt in ('-T', '--dataTime'):
                self._params['parameter.dataTime'] = val
            elif opt in ('-f', '--fmap'):
                self._params['outMaps.fmap'] = val
            elif opt in ('-x', '--ext'):
                self._params['outMaps.ext'] = val
            elif opt in ('-l', '--loggerLevel'):
                self._params['logger.level'] = val
            elif opt in ('-d', '--outLogDir'):
                self._params['logger.dir'] = val
            elif opt in ('-o', '--outDir'):
                self._params['outMaps.outDir'] = val
            elif opt in ('-m', '--perturbationNumber'):
                self._params['parameter.perturbationNumber'] = val
            elif opt in ('-I', '--inputFile2'):
                self._params['input.file2'] = val
                self._params['input.two_resolution'] = True
            elif opt in ('-g', '--addGeopotential'):
                self._params['geopotential'] = val
                self._addGeopotential = True
            elif opt in ('-t', '--test'):
                self._params['test.xml'] = val
            elif opt in ('-h', '--help'):
                self._showHelp = True

        global global_out_log_dir
        global_out_log_dir = self._params['logger.dir']

        global global_main_logger
        global_main_logger = Logger('application', loggingLevel=self.get('logger.level'))
        self._logger = Logger('ExecutionContext', loggingLevel=self.get('logger.level'))
        global global_logger_level
        global_logger_level = self._params['logger.level']

    def get(self, param):
        return self._params[param] if param in self._params else None

    #will read the xml commands file and store parameters
    def _define_exec_params(self):
        dir_ = os.path.dirname(__file__)
        self._params['execution.doAggregation'] = False
        self._params['execution.doConversion'] = False
        self._params['execution.doCorrection'] = False
        self._params['parameter.conversionId'] = None
        #added on 16th july (v1.01)
        if self._inputArguments['commandsFile'].startswith('./') or self._inputArguments['commandsFile'].startswith('../'):
            self._inputArguments['commandsFile'] = os.path.join(os.getcwd(), self._inputArguments['commandsFile'])
        param_xml_path = os.path.join(dir_, '../../' + PARAMETERS_XML)
        time.strftime('%l:%M%p %Z on %b %d, %Y')  # ' 1:36PM EDT on Oct 18, 2010'
         # ' 1:36PM EST on Oct 18, 2010'
        self._log('\n\n\n\nFirst debug message. pyg2p execution started at (%s).\n %s loading...' %(time.strftime('%l:%M%p %z on %b %d, %Y'), self._inputArguments['commandsFile']))
        if not Fm.exists(self._inputArguments['commandsFile']):
            raise ApplicationException.get_programmatic_exc(0, self._inputArguments['commandsFile'])
        u = untangle.parse(self._inputArguments['commandsFile'])
        self._log(self._inputArguments['commandsFile'] + ' done!')

        self._params['execution.name'] = u.Execution['name']
        self._params['execution.id'] = u.Execution['id']

        self._params['parameter.shortName'] = u.Execution.Parameter['shortName']
        self._log(param_xml_path + ' loading...')
        p = untangle.parse(param_xml_path)
        self._log(param_xml_path + ' done!')

        parameter_from_xml = self._read_parameter_from(p, self._params['parameter.shortName'])
        self._params['parameter.description'] = parameter_from_xml['description']
        self._params['parameter.unit'] = parameter_from_xml['unit']
        self._params['parameter.conversionUnit'] = parameter_from_xml['unit']
        if u.Execution.Parameter['applyConversion']:
            self._params['execution.doConversion'] = True
            self._params['parameter.conversionId'] = u.Execution.Parameter['applyConversion']
            conversion_from_xml = self._read_conversion(parameter_from_xml, self._params['parameter.conversionId'])
            self._params['parameter.conversionUnit'] = conversion_from_xml['unit']
            self._params['parameter.conversionFunction'] = conversion_from_xml['function']
            self._params['parameter.cutoffnegative'] = Fsc.to_boolean(conversion_from_xml['cutOffNegative'])

        if u.Execution.Parameter['correctionFormula'] and u.Execution.Parameter['gem'] and u.Execution.Parameter['demMap']:
            self._params['execution.doCorrection'] = True
            self._params['correction.formula'] = u.Execution.Parameter['correctionFormula']
            self._params['correction.gemFormula'] = u.Execution.Parameter['gem']
            self._params['correction.demMap'] = u.Execution.Parameter['demMap']

        #self._params['outMaps.outDir'] = u.Execution.OutMaps['outDir']
        self._params['outMaps.clone'] = u.Execution.OutMaps['cloneMap']

        self._params['interpolation.mode'] = u.Execution.OutMaps.Interpolation['mode'] if u.Execution.OutMaps.Interpolation['mode'] else DEFAULT_VALUES['interpolation.mode'] #must be recognised
        self._params['interpolation.dir'] = u.Execution.OutMaps.Interpolation['intertableDir'] if u.Execution.OutMaps.Interpolation['intertableDir'] else None
        # self._set_additional_interp_attrs(u.Execution.OutMaps.Interpolation)
        self._params['interpolation.latMap'] = u.Execution.OutMaps.Interpolation['latMap']
        self._params['interpolation.lonMap'] = u.Execution.OutMaps.Interpolation['lonMap']

        #optional parameters
        self._params['outMaps.namePrefix'] = u.Execution.OutMaps['namePrefix'] if u.Execution.OutMaps['namePrefix'] else u.Execution.Parameter['shortName']
        self._params['outMaps.unitTime'] = u.Execution.OutMaps['unitTime'] if u.Execution.OutMaps['unitTime'] else None #in hours #number
        #self._params['outMaps.ext'] = u.Execution.OutMaps['ext'] if u.Execution.OutMaps['ext'] else '1' #number
        if self._params['outMaps.fmap'] is None:
            self._params['outMaps.fmap'] = u.Execution.OutMaps['fmap'] if u.Execution.OutMaps['fmap'] is not None else '1' #number
        if self._params['outMaps.ext'] is None:
            self._params['outMaps.ext'] = u.Execution.OutMaps['ext'] if u.Execution.OutMaps['ext'] else '1' #number
        #if start, end and dataTime are defined via command line input args, these are ignored.
        if self._params['parameter.tstart'] is None:
            self._params['parameter.tstart'] = u.Execution.Parameter['tstart'] #number
        if self._params['parameter.tend'] is None:
            self._params['parameter.tend'] = u.Execution.Parameter['tend']  #number
        if self._params['parameter.dataTime'] is None:
            self._params['parameter.dataTime'] = u.Execution.Parameter['dataTime']  #number

        self._params['parameter.level'] = u.Execution.Parameter['level']  #number

        if hasattr(u.Execution, 'Aggregation'):
            self._params['aggregation.step'] = u.Execution.Aggregation['step']
            self._params['aggregation.type'] = u.Execution.Aggregation['type']
            if self._params['aggregation.step'] and self._params['aggregation.type']:
                self._params['execution.doAggregation'] = True
                from gribpcraster.application.manipulation.Manipulator import MANIPULATION_ACCUM
                from util.generics import FALSE_STRINGS
                if self._params['aggregation.type'] == MANIPULATION_ACCUM and u.Execution.Aggregation['forceZeroArray'] and u.Execution.Aggregation['forceZeroArray'] not in FALSE_STRINGS:
                    self._params['aggregation.forceZeroArray'] = True


    def must_do_manipulation(self):
        return self._params['execution.doAggregation']

    def must_do_correction(self):
        return self._params['execution.doCorrection']

    def must_do_conversion(self):
        return self._params['execution.doConversion']

    def is_2_input_files(self):
        return self._params['input.two_resolution']

    # def _set_additional_interp_attrs(self, interp_conf_node):
    #     pass
    #     # for addattrs in KNOWN_INTERP_MODES[self._params['interpolation.mode']]:
    #     #     key = self._params['interpolation.mode'] + '.' + addattrs
    #     #     self._params[key] = interp_conf_node[addattrs] if interp_conf_node[addattrs] is not None else DEFAULT_VALUES[key]

    @staticmethod
    def _read_conversion(param_conf_node, conversion_id):
        if isinstance(param_conf_node, collections.Iterable):
            for c in param_conf_node.Conversion:
                if c['id'] == conversion_id:
                    return c
            raise ApplicationException.get_programmatic_exc(1200)
        else:
            c = param_conf_node.Conversion
            if c['id'] == conversion_id:
                return c
        raise ApplicationException.get_programmatic_exc(1200)

    @staticmethod
    def _read_parameter_from(untangled, short_name):

        if isinstance(untangled.Parameters.Parameter, collections.Iterable):
            for p in untangled.Parameters.Parameter:
                if p['shortName'] == short_name:
                    return p
            raise ApplicationException.get_programmatic_exc(1100)
        else:
            p = untangled.Parameters.Parameter
            if p['shortName'] == short_name:
                return p
            raise ApplicationException.get_programmatic_exc(1100)

    def _check_exec_params(self):

        if self.user_wants_to_test():
            if not Fm.exists(self._params['test.xml']):
                raise ApplicationException.get_programmatic_exc(7000, self._params['test.xml'])
        elif self.user_wants_help():
            pass
        elif self.user_wants_to_add_geopotential():
            if not Fm.exists(self._params['geopotential']):
                raise ApplicationException.get_programmatic_exc(7001, self._params['geopotential'])
        else:

            try:
                if not 'input.file' in self._params:
                    raise ApplicationException.get_programmatic_exc(1001)
                if not Fm.exists(self._params['input.file']):
                    raise ApplicationException.get_programmatic_exc(1000,self._params['input.file'])
                if not Fm.exists(self._params['interpolation.lonMap']) or not Fm.exists(self._params['interpolation.latMap']):
                    raise ApplicationException.get_programmatic_exc(1300)
                if not Fm.exists(self._params['outMaps.clone']):
                    raise ApplicationException.get_programmatic_exc(1310)
            except ApplicationException, exc:
                raise exc
            except Exception, exc:
                raise ApplicationException(exc, None, str(exc))

            #create out dir if not existing
            try:
                if self._params['outMaps.outDir'] != './':
                    if not self._params['outMaps.outDir'].endswith('/'):
                        self._params['outMaps.outDir']+='/'
                    if not Fm.exists(self._params['outMaps.outDir'], isDir=True):
                        Fm.createDir(self._params['outMaps.outDir'])
                        self._log('Non existing Output directory: ' + self._params['outMaps.outDir'] + ' - created.')
            except Exception, exc:

                raise ApplicationException(exc, None, str(exc))

            if self._params['interpolation.dir'] is not None and not Fm.exists(self._params['interpolation.dir'], isDir=True):
                raise ApplicationException.get_programmatic_exc(1320, self._params['interpolation.dir'])

            #check all numbers

            try:
                if self._params['parameter.tstart'] is not None and not self._params['parameter.tstart'].isdigit():
                    raise ApplicationException.get_programmatic_exc(1400, 'Start step')
                self._params['parameter.tstart'] = int(self._params['parameter.tstart']) if self._params['parameter.tstart'] is not None else None

                self._params['parameter.dataTime'] = int(self._params['parameter.dataTime']) if self._params['parameter.dataTime'] is not None else None


                if self._params['parameter.tend'] is not None and not self._params['parameter.tend'].isdigit():
                    raise ApplicationException.get_programmatic_exc(1400, 'End step')
                self._params['parameter.tend'] = int(self._params['parameter.tend']) if self._params['parameter.tend'] is not None else None

                if self._params['parameter.level'] and not self._params['parameter.level'].isdigit():
                    raise ApplicationException.get_programmatic_exc(1400, 'Parameter level')
                self._params['parameter.level'] = int(self._params['parameter.level']) if self._params['parameter.level'] is not None else None

                if 'parameter.perturbationNumber' in self._params and not self._params['parameter.perturbationNumber'].isdigit():
                    raise ApplicationException.get_programmatic_exc(1400, 'EPS member')
                self._params['parameter.perturbationNumber'] = int(self._params['parameter.perturbationNumber']) if 'parameter.perturbationNumber' in self._params else None

                if self._params['outMaps.unitTime'] and not self._params['outMaps.unitTime'].isdigit():
                    raise ApplicationException.get_programmatic_exc(1400, 'Output maps unit time')
                self._params['outMaps.unitTime'] = int(self._params['outMaps.unitTime']) if self._params['outMaps.unitTime'] is not None else None

                if self._params['outMaps.fmap'] and not self._params['outMaps.fmap'].isdigit():
                    raise ApplicationException.get_programmatic_exc(1400, 'fmap number')
                if self._params['outMaps.ext'] and not self._params['outMaps.ext'].isdigit():
                    raise ApplicationException.get_programmatic_exc(1400, 'ext number')
                self._params['outMaps.fmap'] = int(self._params['outMaps.fmap'])

                self._params['outMaps.ext'] = int(self._params['outMaps.ext'])
            except Exception, exc:

                raise ApplicationException(exc, None, str(exc))

            # #check inv dist additional params if exist
            #
            # try:
            #
            #     if self._params['interpolation.mode'] in ['invdist', 'nearest']:
            #         if self._params[self._params['interpolation.mode']+'.p'] is not None and not self._params[self._params['interpolation.mode']+'.p'].isdigit():
            #             raise ApplicationException.get_programmatic_exc(1400, 'Interpolation param p')
            #         self._params[self._params['interpolation.mode']+'.p'] = int(self._params[self._params['interpolation.mode']+'.p']) if self._params[self._params['interpolation.mode']+'.p'] is not None else None
            #         if self._params[self._params['interpolation.mode']+'.leafsize'] is not None  and not self._params[self._params['interpolation.mode']+'.leafsize'].isdigit():
            #             raise ApplicationException.get_programmatic_exc(1400, 'Interpolation param leafsize')
            #         self._params[self._params['interpolation.mode']+'.leafsize'] = int(self._params[self._params['interpolation.mode']+'.leafsize']) if self._params[self._params['interpolation.mode']+'.leafsize'] is not None else None
            #         #for float numbers is best to do:
            #         try:
            #             self._params[self._params['interpolation.mode']+'.eps'] = float(self._params[self._params['interpolation.mode']+'.eps']) if self._params[self._params['interpolation.mode']+'.eps'] is not None else None
            #         except ValueError:
            #             raise ApplicationException.get_programmatic_exc(1400, 'Interpolation param eps')
            # except Exception, exc:
            #
            #     raise ApplicationException(exc, None, str(exc))

            try:
                #check tstart<=tend
                if self._params['parameter.tstart'] is not None and self._params['parameter.tend'] is not None and not (self._params['parameter.tstart'] <= self._params['parameter.tend']):
                    raise ApplicationException.get_programmatic_exc(1500)

                # #check interpolation.mode is supported
                # if not KNOWN_INTERP_MODES.has_key(self._params['interpolation.mode']):
                #     raise ApplicationException.get_programmatic_exc(1600, self._params['interpolation.mode'])

                #check both correction params are present
                if self._params['execution.doCorrection'] and not ('correction.gemFormula' in self._params and 'correction.formula' in self._params and  'correction.demMap' in self._params):
                    raise ApplicationException.get_programmatic_exc(4100)
                if self._params['execution.doCorrection'] and not Fm.exists(self._params['correction.demMap']):
                    raise ApplicationException.get_programmatic_exc(4200, self._params['correction.demMap'])
            except Exception, exc:
                raise ApplicationException(exc, None, str(exc))

    def __str__(self):
        mess = '\n\n\n============ grib-pcraster-pie: Execution parameters ' + Du.getNowStr() + ' ================\n\n'

        for par in sorted(self._params.iterkeys()):
            mess += '\n' + par + '=' + str(self._params[par]) if self._params[par] is not None and self._params[par] else ''
        return mess

    def user_wants_help(self):
        return self._showHelp

    def user_wants_to_add_geopotential(self):
        return self._addGeopotential

    def has_perturbation_number(self):
        return 'parameter.perturbationNumber' in self._params and self._params['parameter.perturbationNumber'] is not None

    def create_select_cmd_for_reader(self, start_, end_):
        self._log('\n\n**********Selecting gribs using:************ \n')
        ## 'var' suffix is for multiresolution 240 step message (global EUE files)
        reader_args = {'shortName': [str(self._params['parameter.shortName']), str(self._params['parameter.shortName'] + 'var')]}
        self._log('---variable short name = %s' % reader_args['shortName'])
        if self._params['parameter.level'] is not None:
            reader_args['level'] = self._params['parameter.level']
            self._log('---level = %d'%self._params['parameter.level'])
        if self._params['parameter.dataTime'] is not None:
            reader_args['dataTime'] = self._params['parameter.dataTime']
            self._log('---dataTime = %s'%self._params['parameter.dataTime'])

        if self.has_perturbation_number():
            reader_args['perturbationNumber'] = self._params['parameter.perturbationNumber']
            self._log('---eps Member (perturbationNumber) = %d' % self._params['parameter.perturbationNumber'])

        #start_step, end_step
        if start_ == end_:
            reader_args['endStep'] = end_
            reader_args['startStep'] = start_
            self._log('---startStep = %d'%start_)
            self._log('-----endStep = %d\n\n'%end_)
        else:
            reader_args['endStep'] = lambda s: s <= end_
            reader_args['startStep'] = lambda s: s >= start_
            self._log('---startStep >= %d'%start_)
            self._log('-----endStep <= %d\n\n'%end_)
        return reader_args

    def create_select_cmd_for_aggregation_attrs(self):

        reader_arguments = {'shortName': str(self._params['parameter.shortName'])}
        if 'parameter.perturbationNumber' in self._params and self._params['parameter.perturbationNumber'] is not None:
            reader_arguments['perturbationNumber'] = self._params['parameter.perturbationNumber']
        return reader_arguments

    def user_wants_to_test(self):
        return 'test.xml' in self._params and self._params['test.xml'] is not None
