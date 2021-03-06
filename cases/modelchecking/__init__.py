from cases import tools, TempObj, PBESCase, LPSTOOLS_MEMLIMIT, LPSTOOLS_TIMEOUT
import specs
import os.path
import logging
import tempfile
import re
import sys
import multiprocessing
import traceback

class Property(PBESCase):
  def __init__(self, description, lps, mcf, temppath, outpath):
    super(Property, self).__init__()
    self.__desc = description
    self._outpath = outpath
    self._temppath = temppath
    self._prefix = self.__desc + '_' + os.path.splitext(os.path.split(mcf)[1])[0]
    self.lps = lps
    self.mcffile = mcf
    self.renfile = os.path.splitext(self.mcffile)[0] + '.ren'
    self.result['property'] = str(self)
  
  def _properties(self):
      return (self.__desc, self.lps, self.mcffile, 
             self._temppath, self._outpath)
  
  def __str__(self):
    return os.path.splitext(os.path.split(self.mcffile)[1])[0]
  
  def _rename(self):
    '''If a lpsactionrename specification exists for this property, transform
       the LPS.'''
    if os.path.exists(self.renfile):
      result = tools.lpsactionrename('-f', self.renfile, '-v', stdin=self.lps, memlimit=LPSTOOLS_MEMLIMIT, timeout=LPSTOOLS_TIMEOUT)['out']
      self.lps = result
  
  def _makePBES(self):
    '''Generate a PBES out of self.lps and self.mcffile, and apply pbesconstelm
       to it.'''
    self._rename()
    result = tools.lps2pbes('-f', self.mcffile, '-v', stdin=self.lps, memlimit=LPSTOOLS_MEMLIMIT, timeout=LPSTOOLS_TIMEOUT)['out']
    result = tools.pbesconstelm('-v', stdin=result, memlimit=LPSTOOLS_MEMLIMIT, timeout=LPSTOOLS_TIMEOUT)['out']
    return result

class Case(TempObj):
  def __init__(self, name, **kwargs):
    TempObj.__init__(self)
    spec = specs.get(name)
    self.__name = name
    self.__kwargs = kwargs
    self._mcrl2 = spec.mcrl2(**kwargs)
    self._outpath = os.path.join(os.path.split(__file__)[0], 'data')
    self._temppath = os.path.join(os.path.split(__file__)[0], 'temp')
    self._prefix = '{0}{1}'.format(self.__name, ('_'.join('{0}={1}'.format(k,v) for k,v in self.__kwargs.items())))
    self.proppath = os.path.join(os.path.split(__file__)[0], 'properties', spec.TEMPLATE)
    self.result = {}
    self.result['case'] = str(self)
    self.result['properties'] = []
      
  def __str__(self):
    argstr = ', '.join(['{0}={1}'.format(k, v) for k, v in self.__kwargs.items()])
    return '{0}{1}'.format(self.__name, ' [{0}]'.format(argstr) if argstr else '')

  def _makeLPS(self, log):
    '''Linearises the specification in self._mcrl2.'''
    log.debug('Linearising {0}'.format(self))
    result = tools.mcrl22lps('-vnf', stdin=self._mcrl2, memlimit=LPSTOOLS_MEMLIMIT, timeout=LPSTOOLS_TIMEOUT)['out']
    return result
  
  def phase0(self, log):
    '''Generates an LPS and creates subtasks for every property that should be
    verified.'''
    try:
      lps = self._makeLPS(log)    
      for prop in os.listdir(self.proppath):
        if not prop.endswith('.mcf'):
          continue
        self.subtasks.append(Property(self._prefix, lps, os.path.join(self.proppath, prop), 
                                      self._temppath, self._outpath))
    except tools.ToolException as e:
      log.error('Exception while creating LPS for {0}, exception was {1}'.format(self, e))
      raise e
      
      
  def phase1(self, log):
    for r in self.results:
      self.result['properties'].append(r.result)
    
class IEEECase(Case):
  def _makeLPS(self, log):
    '''Linearises the specification in self._mcrl2 and applies lpssuminst to the
    result.'''
    log.debug('Linearising {0}'.format(self))
    result = tools.mcrl22lps('-vnf', stdin=self._mcrl2, memlimit=LPSTOOLS_MEMLIMIT, timeout=LPSTOOLS_TIMEOUT)['out']
    log.debug('Applying suminst on LPS of {0}'.format(self))
    result = tools.lpssuminst(stdin=result, memlimit=LPSTOOLS_MEMLIMIT, timeout=LPSTOOLS_TIMEOUT)['out']
    return result

class GameCase(Case):
  def __init__(self, name, use_compiled_constelm=False, **kwargs):
    super(GameCase, self).__init__(name, **kwargs)
    self.__boardwidth = kwargs.get('width')
    self.__boardheight = kwargs.get('height')
    self.__use_compiled_constelm = use_compiled_constelm
    
  def _makeLPS(self, log):
    '''Linearises the specification in self._mcrl2 and applies lpssuminst,
    lpsparunfold and lpsconstelm to the result.'''
    log.debug('Linearising {0}'.format(self))
    result = tools.mcrl22lps('-vnf', stdin=self._mcrl2, memlimit=LPSTOOLS_MEMLIMIT, timeout=LPSTOOLS_TIMEOUT)['out']
    log.debug('Applying suminst on LPS of {0}'.format(self))
    result = tools.lpssuminst(stdin=result, memlimit=LPSTOOLS_MEMLIMIT, timeout=LPSTOOLS_TIMEOUT)['out']
    log.debug('Applying parunfold (for Board) on LPS of {0}'.format(self))
    result = tools.lpsparunfold('-lv', '-n{0}'.format(self.__boardheight), '-sBoard', stdin=result, memlimit=LPSTOOLS_MEMLIMIT, timeout=LPSTOOLS_TIMEOUT)['out']
    log.debug('Applying parunfold (for Row) on LPS of {0}'.format(self))
    result = tools.lpsparunfold('-lv', '-n{0}'.format(self.__boardwidth), '-sRow', stdin=result, memlimit=LPSTOOLS_MEMLIMIT, timeout=LPSTOOLS_TIMEOUT)['out']
    log.debug('Applying constelm on LPS of {0}'.format(self))
    result = tools.lpsconstelm('-ctvrjittyc' if self.__use_compiled_constelm else '-ctv', stdin=result, memlimit=LPSTOOLS_MEMLIMIT, timeout=LPSTOOLS_TIMEOUT)['out']
    return result

def getcases(debugOnly = False):
  if(debugOnly):
    return \
      [Case('Debug spec')] + \
      [Case('ABP', datasize=2)] + \
      [Case('ABP(BW)', datasize=2)] + \
      [Case('CABP', datasize=2)] + \
      [Case('Par', datasize=2)]
  
  return \
    [Case('Debug spec')] + \
    [Case('Lift (Correct)', nlifts=n) for n in range(2, 5)] + \
    [Case('Lift (Incorrect)', nlifts=n) for n in range(2, 5)] + \
    [Case('ABP', datasize=i) for i in [2,4,8]] + \
    [Case('ABP(BW)', datasize=i) for i in [2,4,8]] + \
    [Case('CABP', datasize=i) for i in [2,4,8]] + \
    [Case('Par', datasize=i) for i in [2,4,8]] + \
    [IEEECase('IEEE1394', nparties=2, datasize=2, headersize=2, acksize=2)] + \
    [Case('SWP', windowsize=1, datasize=i) for i in [2,4,8] ] + \
    [Case('SWP', windowsize=2, datasize=i) for i in [2,4] ] + \
    [Case('Leader', nparticipants=n) for n in range(3, 7)] + \
    [GameCase('Clobber', width=w, height=h) for (w,h) in [(4,4)] ] + \
    [GameCase('Snake', width=w, height=h) for (w,h) in [(4,4)] ] + \
    [GameCase('Hex', width=w, height=h) for (w,h) in [(4,4)] ] + \
    [GameCase('Domineering', width=w, height=h) for (w,h) in [(4,4) ] ] + \
    [Case('Hanoi', ndisks=n) for n in range(8,14)] + \
    [Case('Elevator', policy=p, storeys=n) for p in ['FIFO', 'LIFO'] for n in range(2,9)] + \
    [Case('CCP')] + \
    [Case('Hesselink', datasize=i) for i in range(2,5) ] + \
    [Case('Onebit', datasize=i) for i in [2,3]] + \
    [Case('BRP', datasize=i) for i in [2,4]] + \
    [Case('SWP', windowsize=3, datasize=i) for i in [2,4] ] + \
    [Case('SWP', windowsize=4, datasize=i) for i in [2] ]
#    [GameCase('Othello', width=4, height=4)] + """ \
    