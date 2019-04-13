"""Detect from trajectory."""
import pickle
from abc import ABCMeta, abstractmethod
from enum import Enum, auto

import openbabel
from .dps import dps as connectmolecule


class Detect(metaclass=ABCMeta):
    def __init__(self, filename, atomname):
        self.filename = filename
        self.steplinenum = self._readN()
        self.atomname = atomname

    @abstractmethod
    def _readN(self):
        pass

    @abstractmethod
    def readatombondtype(self, item):
        """This function reads bond types of atoms such as C1111."""
        pass

    @abstractmethod
    def readmolecule(self, lines):
        """This function reads molecules."""
        pass
    
    @staticmethod
    def gettype(inputtype):
        """Get the class for the input file type."""
        if inputtype == 'bond':
            detectclass = _DetectBond
        elif inputtype == 'dump':
            detectclass = _DetectDump
        else:
            raise RuntimeError("Wrong input file type")
        return detectclass


class DetectBond(Detect):
    """LAMMPS bond file."""

    def _readN(self):
        """Read bondfile N, which should be at very beginning."""
        # copy from reacnetgenerator on 2018-12-15
        with open(self.filename) as f:
            iscompleted = False
            for index, line in enumerate(f):
                if line.startswith("#"):
                    if line.startswith("# Number of particles"):
                        if iscompleted:
                            stepbindex = index
                            break
                        else:
                            iscompleted = True
                            stepaindex = index
                        N = [int(s) for s in line.split() if s.isdigit()][0]
                        atomtype = np.zeros(N, dtype=np.int)
                else:
                    s = line.split()
                    atomtype[int(s[0])-1] = int(s[1])
        steplinenum = stepbindex-stepaindex
        self._N = N
        self.atomtype = atomtype
        self.atomnames = self.atomname[self.atomtype-1]
        return steplinenum
    
    def readatombondtype(self, item):
        # copy from reacnetgenerator on 2018-12-15
        (step, lines), _ = item
        d = defaultdict(list)
        for line in lines:
            if line:
                if line[0] != "#":
                    s = line.split()
                    atombond = sorted(
                        map(lambda x: max(1, round(float(x))), s[4 + int(s[2]): 4 + 2 * int(s[2])]))
                    d[pickle.dumps((self.atomnames[int(s[0]) - 1],
                                    atombond))].append(int(s[0]))
        return d, step
    
    def readmolecule(self, lines):
        # copy from reacnetgenerator on 2018-12-15
        bond = [None]*self._N
        for line in lines:
            if line:
                if not line.startswith("#"):
                    s = line.split()
                    bond[int(s[0])-1] = map(lambda x: int(x) -
                                            1, s[3:3+int(s[2])])
        molecules = connectmolecule(bond)
        return molecules

class DetectDump(Detect):
    def _readN(self):
        # copy from reacnetgenerator on 2018-12-15
        iscompleted = False
        for index, line in enumerate(f):
            if line.startswith("ITEM:"):
                linecontent = self.LineType.linecontent(line)
            else:
                if linecontent == self.LineType.NUMBER:
                    if iscompleted:
                        stepbindex = index
                        break
                    else:
                        iscompleted = True
                        stepaindex = index
                    N = int(line.split()[0])
                    atomtype = np.zeros(N, dtype=int)
                elif linecontent == self.LineType.ATOMS:
                    s = line.split()
                    atomtype[int(s[0])-1] = int(s[1])-1
        steplinenum = stepbindex-stepaindex
        self._N = N
        self.atomtype = atomtype
        self.atomnames = self.atomname[self.atomtype-1]
        return steplinenum
    
    def readatombondtype(self, item):
        (step, _), _ = item
        d = defaultdict(list)
        step_atoms = self.readcrd(item)
        level = self._crd2bond(step_atoms, readlevel=True)
        for (i, n), l in enumerate(self.atomnames), level:
            # Note that atom id starts from 1
            d[pickle.dumps((n, sorted(l)))].append(i+1)
        return d, step
    
    def readmolecule(self, lines):
        bond = [None]*self._N
        step_atoms = self.readcrd(((item, None), None))
        bond = self._crd2bond(step_atoms, readlevel=False)
        molecules = connectmolecule(bond)
        # return atoms as well
        return molecules, step_atoms

    @classmethod
    def _crd2bond(cls, step_atoms, readlevel):
        # copy from reacnetgenerator on 2019/4/13
        atomnumber = len(step_atoms)
        xyzstring = ''.join((f"{atomnumber}\n{__name__}\n", "\n".join(
            [f'{s:2s} {x:22.15f} {y:22.15f} {z:22.15f}'
             for s, (x, y, z) in zip(
                 step_atoms.get_chemical_symbols(),
                 step_atoms.positions)])))
        conv = openbabel.OBConversion()
        conv.SetInAndOutFormats('xyz', 'mol2')
        mol = openbabel.OBMol()
        conv.ReadString(mol, xyzstring)
        mol2string = conv.WriteString(mol)
        linecontent = -1
        if readlevel:
            bondlevel = [[] for i in range(atomnumber)]
        else:
            bond = [[] for i in range(atomnumber)]
        for line in mol2string.split('\n'):
            if line.startswith("@<TRIPOS>BOND"):
                linecontent = 0
            else:
                if linecontent == 0:
                    s = line.split()
                    if len(s) > 3:
                        b1, b2 = int(s[1])-1, int(s[2])-1
                        if readlevel:
                            level = 9 if s[3] == 'ar' else int(s[3])
                            bondlevel[b1].append(level)
                            bondlevel[b2].append(level)
                        else:
                            bond[b1].append(b2)
                            bond[b2].append(b1)
        return bondlevel if readlevel else bond
    
    def readcrd(self, item):
        """Only this function can read coordinates."""
        (_, lines), _ = item
        boxsize = []
        step_atoms = []            
        for line in lines:
            if line:
                if line.startswith("ITEM:"):
                    linecontent = self.LineType.linecontent(line)
                else:
                    if linecontent == self.LineType.ATOMS:
                        s = line.split()
                        step_atoms.append(
                            (int(s[0]),
                             Atom(
                                 self.atomname[int(s[1]) - 1],
                                 tuple(map(float, s[2: 5])))))
                    elif linecontent == self.LineType.BOX:
                        s = line.split()
                        boxsize.append(float(s[1])-float(s[0]))
                    elif linecontent == self.LineType.TIMESTEP:
                        timestep = step, int(line.split()[0])
        # sort by ID
        _, step_atoms = zip(*sorted(step_atoms, key=lambda a: a[0]))
        step_atoms = Atoms(step_atoms, cell=boxsize, pbc=self.pbc)
        return step_atoms
    
    class LineType(Enum):
        """Line type in the LAMMPS dump files."""

        TIMESTEP = auto()
        ATOMS = auto()
        NUMBER = auto()
        BOX = auto()
        OTHER = auto()

        @classmethod
        def linecontent(cls, line):
            """Return line content."""
            if line.startswith("ITEM: TIMESTEP"):
                return cls.TIMESTEP
            if line.startswith("ITEM: ATOMS"):
                return cls.ATOMS
            if line.startswith("ITEM: NUMBER OF ATOMS"):
                return cls.NUMBER
            if line.startswith("ITEM: BOX"):
                return cls.BOX
            return cls.OTHER
    class LineType(Enum):
        """Line type in the LAMMPS dump files."""

        TIMESTEP = auto()
        ATOMS = auto()
        NUMBER = auto()
        BOX = auto()
        OTHER = auto()

        @classmethod
        def linecontent(cls, line):
            """Return line content."""
            if line.startswith("ITEM: TIMESTEP"):
                return cls.TIMESTEP
            if line.startswith("ITEM: ATOMS"):
                return cls.ATOMS
            if line.startswith("ITEM: NUMBER OF ATOMS"):
                return cls.NUMBER
            if line.startswith("ITEM: BOX"):
                return cls.BOX
            return cls.OTHERms, cell=boxsize, pbc=self.pbc)
        return step_atoms
    
    class LineType(Enum):
        """Line type in the LAMMPS dump files."""

        TIMESTEP = auto()
        ATOMS = auto()
        NUMBER = auto()
        BOX = auto()
        OTHER = auto()

        @classmethod
        def linecontent(cls, line):
            """Return line content."""
            if line.startswith("ITEM: TIMESTEP"):
                return cls.TIMESTEP
            if line.startswith("ITEM: ATOMS"):
                return cls.ATOMS
            if line.startswith("ITEM: NUMBER OF ATOMS"):
                return cls.NUMBER
            if line.startswith("ITEM: BOX"):
                return cls.BOX
            return cls.OTHER    """Line type in the LAMMPS dump files."""

        TIMESTEP = auto()
        ATOMS = auto()
        NUMBER = auto()
        BOX = auto()
        OTHER = auto()

        @classmethod
        def linecontent(cls, line):
            """Return line content."""
            if line.startswith("ITEM: TIMESTEP"):
                return cls.TIMESTEP
            if line.startswith("ITEM: ATOMS"):
                return cls.ATOMS
            if line.startswith("ITEM: NUMBER OF ATOMS"):
                return cls.NUMBER
            if line.startswith("ITEM: BOX"):
                return cls.BOX
            return cls.OTHER