import re
import textwrap
from jinja2 import Template as jinjaTemplate
from operator import itemgetter
from collections import namedtuple, defaultdict


class Dumper:

    __ignore_list__ = 'migrations'

    column_record = namedtuple('Record', ['name', 'ttype', 'precision',
                                          'nullable', 'default'])

    foreign_key_record = namedtuple('Record', ['to_table', 'column',
                                               'ref_key', 'name',
                                               'on_update', 'on_delete'])
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
        'INTEGER': 'integer',
        'JSON': 'json',
        'LONGTEXT': 'long_text',
        'MEDIUMINT': 'medium_int',
        'MEDIUMTEXT': 'medium_text',
        'SMALLINT': 'small_int',
        'TEXT': 'text',
        'TIME': 'time',
        'TINYINT': 'tiny_int',
        'TIMESTAMP WITHOUT TIME ZONE': 'timestamp',
        'CHARACTER VARYING': 'string',
        'BIGSERIAL': 'big_increments',
        'SERIAL': 'increments'
    }

    table_tmpl = jinjaTemplate(textwrap.dedent("""\
        with self.schema.create('{{ table_name }}') as table:
            {% for statement in table_statement %}
                {{- statement }}
            {% endfor %}
    """))

    schema_tmpl = jinjaTemplate(textwrap.dedent("""\
    from orator.migrations import Migration


    class InitDb(Migration):
        def up(self):
            {% for table in tables_created %}
                {{- table | indent(8) }}
            {% endfor %}

        def down(self):
            {% for table in tables_droped -%}
                self.schema.drop('{{ table }}')
            {% endfor %}
    """))

    def __init__(self, conn, grammar, db_name):
        """
        @param grammar: grammar instance
        """
        self._conn = conn
        self._grammar = grammar
        self._db_name = db_name

    def handle_column(self, columns):
        statements = []
        for column in columns:
            column_buffer = []
            name = column.name
            ttype = self.mapping[column.ttype.upper()]
            nullable = column.nullable
            default = column.default

            # dump to orator schema syntax
            column_buffer.append('self.{ttype}({name})'.format(
                ttype=ttype, name=repr(name)))
            if nullable != 'NO':
                column_buffer.append('.nullable()')
            if default is not None:
                flag = True
                # ignore timestamp type default value CURRENT_TIMESTAMP(6)
                if ttype == 'timestamp' and 'timestamp' in default:
                    flag = False

                if re.match(r'\w+(\w+)', default):
                    flag = False

                if flag:
                    column_buffer.append('.default({})'.format(
                        default.split(':')[0]))

            statements.append(''.join(column_buffer))
        return statements

    def handle_index(self, indexes):
        statements = []
        for name, index in indexes.items():
            ttype = index['ttype']
            if ttype == 'primary':
                name = None

            statements.append(
                'self.{}({}, name={})'.format(ttype, repr(index['columns']),
                                              repr(name)))
        return statements

    def handle_foreign_key(self, foreign_keys):
        statements = []
        for foreign_key in foreign_keys:
            local_key = foreign_key.column
            ref_key = foreign_key.ref_key
            to_table = foreign_key.to_table
            if foreign_key.on_update == 'a':
                on_update = 'restrict'
            else:
                on_update = 'cascade'
            if foreign_key.on_delete == 'a':
                on_delete = 'restrict'
            else:
                on_delete = 'cascade'

            statement = ('self.foreign({}).references({}).on({})'
                         '.on_update({}).on_delete({})').format(
                             repr(local_key), repr(ref_key),
                             repr(to_table), repr(on_update),
                             repr(on_delete)
            )
            statements.append(statement)
        return statements

    def dump(self):
        table_names = list(self.list_tables())

        table_buffer = []
        for table in table_names:
            columns = self.list_columns(table)
            indexes = self.list_indexes(table)
            foreign_keys = self.list_foreign_keys(table)
            statement_buffer = []

            statement_buffer.extend(self.handle_column(columns))
            statement_buffer.extend(self.handle_index(indexes))
            statement_buffer.extend(self.handle_foreign_key(foreign_keys))

            table_buffer.append(self.table_tmpl.render(
                table_name=table,
                table_statement=statement_buffer
            ))

        output = self.schema_tmpl.render(
            tables_created=table_buffer,
            tables_droped=table_names
        )
        return output

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
        return [self.column_record(*r) for r in result]

    def list_indexes(self, table_name):
        """list index in table"""
        sql = self._grammar._list_indexes(table_name)
        result = self._conn.select(sql)
        indexes = defaultdict(lambda: {'columns': [], 'ttype': 'index'})
        for r in result:
            index = indexes[r[0]]
            index['columns'].extend(r[1].split(', '))
            if r[2] == 'u':
                index['ttype'] = 'unique'
            if r[2] == 'p':
                index['ttype'] = 'primary'
        return indexes

    def list_foreign_keys(self, table_name):
        """list foreign key from specified table"""
        sql = self._grammar._list_foreign_keys(table_name)
        result = self._conn.select(sql)
        return [self.foreign_key_record(*r) for r in result]
