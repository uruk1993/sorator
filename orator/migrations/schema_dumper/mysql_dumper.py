from operator import itemgetter
from collections import namedtuple, defaultdict
from .dumper_interface import Dumper as BaseDumper


class Dumper(BaseDumper):

    __ignore_list__ = 'migrations'

    column_record = namedtuple('Record', ['name', 'ttype', 'precision',
                                          'unsigned', 'nullable', 'default',
                                          'extra'])

    mapping = {
        'BIGINT': 'big_integer',
        'BLOB': 'binary',
        'BOOLEAN': 'boolean',
        'CHAR': 'char',
        'DATE': 'date',
        'DATETIME': 'datetime',
        'DECIMAL': 'decimal',
        'DOUBLE': 'double',
        'ENUM': 'enum',
        'FLOAT': 'float',
        'INT': 'integer',
        'JSON': 'json',
        'LONGTEXT': 'long_text',
        'MEDIUMINT': 'medium_int',
        'MEDIUMTEXT': 'medium_text',
        'SMALLINT': 'small_int',
        'TEXT': 'text',
        'TIME': 'time',
        'TINYINT': 'tiny_int',
        'TIMESTAMP': 'timestamp',
        'VARCHAR': 'string'
    }

    def handle_column(self, columns):
        statements = []
        for column in columns:
            column_buffer = []
            name = column.name
            ttype = self.mapping[column.ttype.upper()]
            unsigned = column.unsigned

            # bigint auto_increment -> big_increments
            # int auto_increment -> increments
            if column.extra == 'auto_increment':
                if ttype == 'big_integer':
                    ttype = 'big_increments'
                if ttype == 'integer':
                    ttype = 'increments'

            # tiny_int when length is 1 -> boolean
            if ttype == 'tiny_int' and column.precision == 1:
                ttype = 'boolean'

            nullable = column.nullable
            default = column.default

            # dump to orator schema syntax
            column_buffer.append('self.{ttype}({name})'.format(
                ttype=ttype, name=repr(name)))
            if unsigned == 'unsigned':
                column_buffer.append('.unsigned()')
            if nullable != 'NO':
                column_buffer.append('.nullable()')
            if default is not None:
                flag = True
                # ignore timestamp type default value CURRENT_TIMESTAMP(6)
                if ttype == 'timestamp' and \
                        default.startswith('CURRENT_TIMESTAMP'):
                    flag = False

                if flag:
                    column_buffer.append('.default({})'.format(default))
            statements.append(''.join(column_buffer))
        return statements

    def handle_index(self, indexes):
        statements = []
        for name, index in indexes.items():
            ttype = 'index'
            if index['is_unique']:
                ttype = 'unique'
            if name == 'PRIMARY':
                ttype = 'primary'
                name = None

            statements.append(
                'self.{}({}, name={})'.format(ttype,
                                              repr(index['columns']),
                                              repr(name)))
        return statements

    def handle_foreign_key(self, foreign_keys):
        statements = []
        for foreign_key in foreign_keys:
            # name = foreign_key['name']
            local_key = foreign_key['column']
            ref_key = foreign_key['ref_key']
            to_table = foreign_key['to_table']
            on_update = foreign_key['on_update']
            on_delete = foreign_key['on_delete']

            statement = 'self.foreign({}).references({}).on({})'.format(
                repr(local_key), repr(ref_key), repr(to_table))

            if on_update.upper() == 'CASCADEA':
                statement += ".on_update('CASCADEA')"

            if on_delete.upper() == 'CASCADEA':
                statement += ".on_delete('CASCADEA')"

            statements.append(statement)
        return statements

    def list_tables(self):
        """list all table_names from specified database
        rtype [str]
        """
        sql = self._grammar._list_tables()
        result = self._conn.select(sql)
        return filter(
            lambda table_name: table_name not in self.__ignore_list__,
            map(itemgetter('table_name'), result))

    def list_columns(self, table_name):
        """list column in table
        rtype [namedtuple]"""
        sql = self._grammar._list_columns(table_name)
        result = self._conn.select(sql)
        print(result)
        return [self.column_record(**r) for r in result]

    def list_indexes(self, table_name):
        """list index in table"""
        sql = self._grammar._list_indexes(table_name)
        result = self._conn.select(sql)
        indexes = defaultdict(lambda: {'columns': [], 'is_unique': False})
        for r in result:
            index = indexes[r['Key_name']]
            index['columns'].append(r['Column_name'])
            if r['Non_unique']:
                index['is_unique'] = True
        return indexes

    def list_foreign_keys(self, table_name):
        """list foreign key from specified table"""
        sql = self._grammar._list_foreign_keys(table_name)
        result = self._conn.select(sql)
        return result
