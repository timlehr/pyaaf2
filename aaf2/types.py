from __future__ import (
    unicode_literals,
    absolute_import,
    print_function,
    division,
    )
import sys
from uuid import UUID
from . import core
from . import properties
from .mobid import MobID
from .rational import AAFRational
from .exceptions import AAFPropertyError

import datetime

from struct import (unpack, pack)
from .utils import register_class, decode_utf16le, encode_utf16le, encode_utf16_array

if sys.version_info.major >= 3:
    unicode = str

PID_NAME      = 0x0006
PID_UUID      = 0x0005

@register_class
class TypeDef(core.AAFObject):
    class_id = UUID("0d010101-0203-0000-060e-2b3402060101")
    __slots__ = ()

    def __new__(cls, root=None, name=None, auid=None, *args, **kwargs):
        self = super(TypeDef, cls).__new__(cls)
        self.root = root
        if root:
            properties.add_string_property(self, PID_NAME, name)
            properties.add_uuid_property(self, PID_UUID, auid)
        return self

    @property
    def unique_key(self):
        return self.auid

    @property
    def auid(self):
        data = self.property_entries[PID_UUID].data
        if data is not None:
            return UUID(bytes_le=self.property_entries[PID_UUID].data)

    @property
    def type_name(self):
        data = self.property_entries[PID_NAME].data
        if data is not None:
            return decode_utf16le(data)

    @property
    def store_format(self):
        return properties.SF_DATA

    def __repr__(self):
        return "<%s %s>" % (self.type_name, self.__class__.__name__)

    def read_properties(self):
        super(TypeDef, self).read_properties()

    def setup_defaults(self):
        return

PID_INT_SIZE   = 0x000F
PID_INT_SIGNED = 0x0010

@register_class
class TypeDefInt(TypeDef):
    class_id = UUID("0d010101-0204-0000-060e-2b3402060101")
    __slots__ = ()
    def __new__(cls, root=None, name=None, auid=None, size=None, signed=None):
        self = super(TypeDefInt, cls).__new__(cls, root, name, auid)
        if root:
            properties.add_u8_property(self, PID_INT_SIZE, size)
            properties.add_bool_property(self, PID_INT_SIGNED, signed)
        return self

    @property
    def signed(self):
        return self.property_entries[PID_INT_SIGNED].data == b"\x01"

    @property
    def size(self):
        data  = self.property_entries[PID_INT_SIZE].data
        if data is not None:
            return unpack('B', data)[0]
        raise ValueError("%s No Size" % str(self.type_name))

    @property
    def byte_size(self):
        return self.size

    def pack_format(self, elements=1):
        fmt = ""
        if self.size == 1:
            fmt = '%dB'
        elif self.size == 2:
            fmt = "<%dH"
        elif self.size == 4:
            fmt = "<%dI"
        elif self.size == 8:
            fmt = "<%dQ"
        else:
            raise AAFPropertyError("unknown integer size: %d" % self.size)
        fmt = fmt % elements
        if self.signed:
            fmt = fmt.lower()

        return str(fmt)

    def decode(self, data):
        assert len(data) == self.size
        return unpack(self.pack_format(), data)[0]

    def encode(self, value):
        return pack(self.pack_format(), value)


PID_STRONGREF_REF_TYPE = 0x0011

@register_class
class TypeDefStrongRef(TypeDef):
    class_id = UUID("0d010101-0205-0000-060e-2b3402060101")
    __slots__ = ()
    def __new__(cls, root=None, name=None, auid=None, classdef=None):
        self = super(TypeDefStrongRef, cls).__new__(cls, root, name, auid)
        if root:
            properties.add_classdef_weakref_property(self, PID_STRONGREF_REF_TYPE, classdef)
        return self

    @property
    def store_format(self):
        return properties.SF_STRONG_OBJECT_REFERENCE

    @property
    def ref_classdef(self):
        if PID_STRONGREF_REF_TYPE in self.property_entries:
             return self.root.metadict.lookup_classdef(self.property_entries[PID_STRONGREF_REF_TYPE].ref)

PID_WEAKREF_REF_TYPE   = 0x0012
PID_WEAKREF_TARGET_SET = 0x0013

@register_class
class TypeDefWeakRef(TypeDef):
    class_id = UUID("0d010101-0206-0000-060e-2b3402060101")
    __slots__ = ()

    def __new__(cls, root=None, name=None, auid=None, classdef=None, path=None):
        self = super(TypeDefWeakRef, cls).__new__(cls, root, name, auid)
        if root:
            properties.add_classdef_weakref_property(self, PID_WEAKREF_REF_TYPE, classdef)
            properties.add_uuid_array_propertry(self, PID_WEAKREF_TARGET_SET, path)

        return self

    @property
    def store_format(self):
        return properties.SF_WEAK_OBJECT_REFERENCE

    @property
    def ref_classdef(self):
        if PID_WEAKREF_REF_TYPE in self.property_entries:
            return self.root.metadict.lookup_classdef(self.property_entries[PID_WEAKREF_REF_TYPE].ref)

    @property
    def path(self):
        return [p.name for c, p in self.propertydef_path]

    @property
    def pid_path(self):
        return [p.pid for c, p in self.propertydef_path]

    @property
    def target_set_path(self):
        return self['TargetSet'].value

    @property
    def propertydef_path(self):
        path = []
        classdef = self.root.metadict.lookup_classdef("Root")
        for auid in self.target_set_path:
            found = False
            for p in classdef.propertydefs:
                if p.uuid == auid:
                    path.append((classdef, p))
                    classdef = p.typedef.ref_classdef
                    found = True
                    break
            if not found:
                raise AAFPropertyError("unable to resolve property path")

        return path

PID_ENUM_TYPE    = 0x0014
PID_ENUM_NAMES   = 0x0015
PID_ENUM_VALUES  = 0x0016

@register_class
class TypeDefEnum(TypeDef):
    class_id = UUID("0d010101-0207-0000-060e-2b3402060101")
    __slots__ = ()
    def __new__(cls, root=None, name=None, auid=None, typedef=None, elements=None):
        self = super(TypeDefEnum, cls).__new__(cls, root, name, auid)
        if root:
            properties.add_typedef_weakref_property(self, PID_ENUM_TYPE, typedef)
            names = []
            values = []
            for val, name in elements.items():
                names.append(name)
                values.append(val)

            properties.add_utf16_array_property(self, PID_ENUM_NAMES, names)
            properties.add_s64_array_property(self, PID_ENUM_VALUES, values)

        return self

    @property
    def byte_size(self):
        return self.element_typedef.byte_size

    @property
    def elements(self):
        names = list(iter_utf16_array(self['ElementNames'].data))
        elements = dict(zip(self['ElementValues'].value, names))
        return elements

    @property
    def element_typedef(self):
        if PID_ENUM_TYPE in self.property_entries:
            return self.root.metadict.lookup_typedef(self.property_entries[PID_ENUM_TYPE].ref)

    def decode(self, data):

        # Boolean
        if self.auid == UUID("01040100-0000-0000-060e-2b3401040101"):
            return data == b'\x01'

        typedef = self.element_typedef
        index = typedef.decode(data)
        return self.elements[index]

    def encode(self, data):
        # Boolean
        if self.auid == UUID("01040100-0000-0000-060e-2b3401040101"):
            return b'\x01' if data else b'\x00'

        typedef = self.element_typedef
        for index, value in self.elements.items():
            if value == data:
                return typedef.encode(index)
            if index == data:
                return typedef.encode(index)

        raise AAFPropertyError("invalid enum: %s" % str(data))

def iter_utf16_array(data):
    start = 0
    data = bytearray(data)
    for i in range(0, len(data), 2):
        if data[i] == 0x00 and data[i+1] == 0x00:
            yield data[start:i].decode("utf-16le")
            start = i+2

PID_FIXED_TYPE  = 0x0017
PID_FIXED_COUNT = 0x0018

@register_class
class TypeDefFixedArray(TypeDef):
    class_id = UUID("0d010101-0208-0000-060e-2b3402060101")
    __slots__ = ()

    def __new__(cls, root=None, name=None, auid=None, typedef=None, size=None):
        self = super(TypeDefFixedArray, cls).__new__(cls, root, name, auid)
        if root:
            properties.add_typedef_weakref_property(self, PID_FIXED_TYPE, typedef)
            properties.add_u32le_property(self, PID_FIXED_COUNT, size)
        return self

    @property
    def element_typedef(self):
        if PID_FIXED_TYPE in self.property_entries:
            return self.root.metadict.lookup_typedef(self.property_entries[PID_FIXED_TYPE].ref)

    @property
    def size(self):
        return unpack('<I', self.property_entries[PID_FIXED_COUNT].data)[0]

    @property
    def byte_size(self):
        return self.element_typedef.byte_size * self.size

    def decode(self, data):
        element_typedef = self.element_typedef

        if isinstance(element_typedef, TypeDefInt):
            size = element_typedef.size
            elements = len(data)//size
            fmt = element_typedef.pack_format(elements)
            return unpack(fmt, data)

        start = 0
        byte_size = element_typedef.byte_size
        result = []
        for i in range(self.size):
            end = start + byte_size
            result.append(element_typedef.decode(data[start:end]))
            start = end

        return result

    def encode(self, data):
        element_typedef = self.element_typedef
        byte_size = element_typedef.byte_size
        element_count = self.size
        result = b""

        for i, item in enumerate(data):
            if i >= element_count:
                raise AAFPropertyError("too many elements for fixed array: expected %d elements" % element_count)
                break
            result += element_typedef.encode(item)

        # zero out remaining bytes
        if i < element_count:
            bytes_left = (element_count - i) * byte_size
            while bytes_left:
                result += b'\0'
                bytes_left -= 1

        return result

PID_VAR_TYPE = 0x0019

@register_class
class TypeDefVarArray(TypeDef):
    class_id = UUID("0d010101-0209-0000-060e-2b3402060101")
    __slots__ = ()

    def __new__(cls, root=None, name=None, auid=None, typedef=None):
        self = super(TypeDefVarArray, cls).__new__(cls, root, name, auid)

        if root:
            properties.add_typedef_weakref_property(self, PID_VAR_TYPE, typedef)
        return self

    @property
    def store_format(self):
        if self.element_typedef.store_format == properties.SF_WEAK_OBJECT_REFERENCE:
            return properties.SF_WEAK_OBJECT_REFERENCE_VECTOR
        elif self.element_typedef.store_format == properties.SF_STRONG_OBJECT_REFERENCE:
            return properties.SF_STRONG_OBJECT_REFERENCE_VECTOR

        return super(TypeDefVarArray, self).store_format

    @property
    def element_typedef(self):
        if PID_VAR_TYPE in self.property_entries:
            return self.root.metadict.lookup_typedef(self.property_entries[PID_VAR_TYPE].ref)

    def decode(self, data):

        element_typedef = self.element_typedef

        #aafCharacter
        if element_typedef.auid == UUID("01100100-0000-0000-060e-2b3401040101"):
            return list(iter_utf16_array(data))


        if isinstance(element_typedef, TypeDefInt):
            size = element_typedef.size
            elements = len(data)//size
            fmt = element_typedef.pack_format(elements)
            return list(unpack(fmt, data))

        byte_size = element_typedef.byte_size
        elements = len(data)//byte_size
        start = 0
        result = []
        for i in range(elements):
            end = start + byte_size
            result.append(element_typedef.decode(data[start:end]))
            start = end
        return result

    def encode(self, value):

        element_typedef = self.element_typedef

        if element_typedef.type_name == "Character":
            return encode_utf16_array(value)

        if isinstance(element_typedef, TypeDefInt):

            elements = len(value)
            fmt = element_typedef.pack_format(elements)
            return pack(fmt, *value)

        result = b''

        for item in value:
            result += element_typedef.encode(item)

        return result

PID_SET_TYPE = 0x001A

@register_class
class TypeDefSet(TypeDef):
    class_id = UUID("0d010101-020a-0000-060e-2b3402060101")
    __slots__ = ()

    def __new__(cls, root=None, name=None, auid=None, typedef=None):
        self = super(TypeDefSet, cls).__new__(cls, root, name, auid)
        if root:
            properties.add_typedef_weakref_property(self, PID_SET_TYPE, typedef)
        return self

    @property
    def element_typedef(self):
        if PID_SET_TYPE in self.property_entries:
            return self.root.metadict.lookup_typedef(self.property_entries[PID_SET_TYPE].ref)

    @property
    def ref_classdef(self):
        typedef = self.element_typedef
        return typedef.ref_classdef

    @property
    def store_format(self):
        if self.element_typedef.store_format == properties.SF_STRONG_OBJECT_REFERENCE:
            return properties.SF_STRONG_OBJECT_REFERENCE_SET
        elif self.element_typedef.store_format == properties.SF_WEAK_OBJECT_REFERENCE:
            return properties.SF_WEAK_OBJECT_REFERENCE_SET
        elif self.element_typedef.store_format == properties.SF_DATA:
            return properties.SF_DATA
        else:
            raise AAFPropertyError("unkown store format: 0x%x" % self.element_typedef.store_format)

    def decode(self, data):

        typedef = self.element_typedef
        byte_size = typedef.byte_size
        count = len(data) // byte_size
        start = 0
        result = set()
        for i in range(count):
            end = start + byte_size
            v = typedef.decode(data[start:end])
            result.add(v)
            start = end

        return result

    def encode(self, data):
        typedef = self.element_typedef

        set_data = set(data)
        result = b""
        for item in set_data:
            result += typedef.encode(item)

        return result

PID_STR_TYPE = 0x001B

@register_class
class TypeDefString(TypeDef):
    class_id = UUID("0d010101-020b-0000-060e-2b3402060101")
    __slots__ = ()

    def __new__(cls, root=None, name=None, auid=None, typedef=None):
        self = super(TypeDefString, cls).__new__(cls, root, name, auid)
        if root:
            properties.add_typedef_weakref_property(self, PID_STR_TYPE, typedef)
        return self

    @property
    def element_typedef(self):
        if PID_STR_TYPE in self.property_entries:
            return self.root.metadict.lookup_typedef(self.property_entries[PID_STR_TYPE].ref)

    def decode(self, data):
        return decode_utf16le(data)

    def encode(self, data):
        return encode_utf16le(data)

@register_class
class TypeDefStream(TypeDef):
    class_id = UUID("0d010101-020c-0000-060e-2b3402060101")

    @property
    def store_format(self):
        return properties.SF_DATA_STREAM

PID_RECORD_TYPES = 0x001C
PID_RECORD_NAMES = 0x001D

@register_class
class TypeDefRecord(TypeDef):
    class_id = UUID("0d010101-020d-0000-060e-2b3402060101")
    __slots__ = ('_fields')

    def __new__(cls, root=None, name=None, auid=None, fields=None):
        self = super(TypeDefRecord, cls).__new__(cls, root, name, auid)
        if root:
            names = []
            types = []
            for name, val in fields:
                names.append(name)
                types.append(val)

            properties.add_utf16_array_property(self, PID_RECORD_NAMES, names)
            properties.add_typedef_weakref_vector_property(self, PID_RECORD_TYPES, 'MemberTypes', types)

        self._fields = None
        return self

    @property
    def fields(self):
        if self._fields:
            return self._fields
        names = list(iter_utf16_array(self['MemberNames'].data))
        types = list(self['MemberTypes'].value)
        self._fields = list(zip(names, [t.type_name for t in types]))
        return self._fields

    @property
    def byte_size(self):
        size = 0
        for key, typedef_name in self.fields:
            typedef = self.root.metadict.typedefs_by_name[typedef_name]
            size += typedef.byte_size
        if size == 0:
            print("!!", self['MemberTypes'].value, list(iter_utf16_array(self['MemberNames'].data)))

        assert size != 0

        return size

    def decode(self, data):

        # MobID
        if self.auid == UUID("01030200-0000-0000-060e-2b3401040101"):
            mobid = MobID(bytes_le=data)
            assert str(mobid) == str(MobID(str(mobid)))
            return mobid

        # AUID
        if self.auid == UUID("01030100-0000-0000-060e-2b3401040101"):
            return UUID(bytes_le=data)

        start = 0
        result = {}

        for key, typedef_name in self.fields:
            typedef = self.root.metadict.lookup_typedef(typedef_name)

            end = start + typedef.byte_size
            result[key] = typedef.decode(data[start:end])
            start = end


        # TimeStruct
        if self.auid == UUID("03010600-0000-0000-060e-2b3401040101"):
            t = datetime.time(result['hour'],
                              result['minute'],
                              result['second'],
                              result['fraction'])
            return t

        # DateStruct
        if self.auid == UUID("03010500-0000-0000-060e-2b3401040101"):
            d = datetime.date(**result)
            return d

        # TimeStamp
        if self.auid == UUID("03010700-0000-0000-060e-2b3401040101"):
            d = datetime.datetime.combine(result['date'], result['time'])
            return d

        # Rational
        if self.auid == UUID("03010100-0000-0000-060e-2b3401040101"):
            r = AAFRational(result['Numerator'], result['Denominator'])
            return r

        return result

    def encode(self, data):
        # MobID
        if self.auid == UUID("01030200-0000-0000-060e-2b3401040101"):
            return data.bytes_le

        # AUID
        if self.auid == UUID("01030100-0000-0000-060e-2b3401040101"):
            return data.bytes_le

        result = b""
        # TimeStamp
        if self.auid == UUID("03010700-0000-0000-060e-2b3401040101"):
            assert isinstance(data, datetime.datetime)
            f = [self.root.metadict.lookup_typedef(t) for k, t in self.fields]
            #date
            result += f[0].encode(data.date())

            #time
            result += f[1].encode(data.time())
            return result


        # DateStruct
        if self.auid == UUID("03010500-0000-0000-060e-2b3401040101"):
            assert isinstance(data, datetime.date)
            d = {'year' : data.year,
                 'month' : data.month,
                 'day': data.day}
            # print (d)
            data = d

        # TimeStruct
        if self.auid == UUID("03010600-0000-0000-060e-2b3401040101"):
            assert isinstance(data, datetime.time)
            t = {'hour' : data.hour,
                 'minute' : data.minute,
                 'second' : data.second,
                 'fraction' : 0 }
            # print(t)
            data = t

        # Rational
        if self.auid == UUID("03010100-0000-0000-060e-2b3401040101"):
            r = AAFRational(data)
            data = {'Numerator': r.numerator, 'Denominator':r.denominator }

        for key, typedef_name in self.fields:
            typedef = self.root.metadict.lookup_typedef(typedef_name)
            value = typedef.encode(data[key])
            result+=value

        return result

PID_RENAME_TYPE = 0x001E

@register_class
class TypeDefRename(TypeDef):
    class_id = UUID("0d010101-020e-0000-060e-2b3402060101")
    def __new__(cls,  root=None, name=None, auid=None, typedef=None):
        self = super(TypeDefRename, cls).__new__(cls, root, name, auid)
        if root:
            properties.add_typedef_weakref_property(self, PID_RENAME_TYPE, typedef)
        return self

    @property
    def renamed_typedef(self):
        if PID_RENAME_TYPE in self.property_entries:
            return self.root.metadict.lookup_typedef(self.property_entries[PID_RENAME_TYPE].ref)

    def decode(self, data):
        return self.renamed_typedef.decode(data)

    def encode(self, data):
        return self.renamed_typedef.encode(data)


@register_class
class TypeDefExtEnum(TypeDef):
    class_id = UUID("0d010101-0220-0000-060e-2b3402060101")
    def __new__(cls, root=None, name=None, auid=None, elements=None):
        self = super(TypeDefExtEnum, cls).__new__(cls, root, name, auid)
        self._elements = {}
        if elements:
            for key,value in elements.items():
                self._elements[UUID(key)] = value
        return self

    def setup_defaults(self):
        super(TypeDefExtEnum, self).setup_defaults()

        names = []
        keys = []
        for key, name in self.elements.items():
            keys.append(key)
            names.append(name)

        self['ElementNames'].add_pid_entry()
        self['ElementNames'].data = encode_utf16_array(names)
        self['ElementValues'].value = keys


    @property
    def elements(self):
        if self._elements:
            return self._elements

        names = list(iter_utf16_array(self['ElementNames'].data))
        keys = list(self['ElementValues'].value)
        return dict(zip(keys, names))


    def decode(self, data):
        if data is None:
            return None
        v = UUID(bytes_le=data)
        result = self.elements.get(v, None)
        if result is None:
            return v

        return result

    def encode(self, data):
        for key, value in self.elements.items():
            if isinstance(data, UUID):
                if data == key:
                    return key.bytes_le
            else:

                if value.lower() == data.lower():
                    return key.bytes_le

        raise ValueError("invalid ext enum value: %s" % str(data))

@register_class
class TypeDefIndirect(TypeDef):
    class_id = UUID("0d010101-0221-0000-060e-2b3402060101")

    def decode_typedef(self, data):
        byte_order = data[0:1]
        assert byte_order == b'\x4c' # little endian
        type_uuid = UUID(bytes_le=data[1:17])
        return self.root.metadict.lookup_typedef(type_uuid)

    def decode(self, data):
        typedef = self.decode_typedef(data)
        result = typedef.decode(data[17:])
        return result

    def encode(self, data, data_typedef=None):
        byte_order = b'\x4c'
        typedef = None
        if data_typedef is not None:
            typedef = self.root.metadict.lookup_typedef(data_typedef)
            if typedef is None:
                raise AAFPropertyError("unable to find typedef: %s" % (str(data_typedef)))
            type_uuid = typedef.auid

        elif isinstance(data, (str, unicode)):
            # aafString
            type_uuid = UUID("01100200-0000-0000-060e-2b3401040101")

        elif isinstance(data, int):
            # aafInt32
            type_uuid = UUID("01010700-0000-0000-060e-2b3401040101")
        else:
            raise NotImplementedError("Indirect type for: %s", str(type(data)))

        if typedef is None:
            typedef = self.root.metadict.lookup_typedef(type_uuid)
        result = byte_order
        result += type_uuid.bytes_le
        result += typedef.encode(data)
        return result



@register_class
class TypeDefOpaque(TypeDefIndirect):
    class_id = UUID("0d010101-0222-0000-060e-2b3402060101")

@register_class
class TypeDefCharacter(TypeDef):
    class_id = UUID("0d010101-0223-0000-060e-2b3402060101")
