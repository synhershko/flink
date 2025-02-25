################################################################################
#  Licensed to the Apache Software Foundation (ASF) under one
#  or more contributor license agreements.  See the NOTICE file
#  distributed with this work for additional information
#  regarding copyright ownership.  The ASF licenses this file
#  to you under the Apache License, Version 2.0 (the
#  "License"); you may not use this file except in compliance
#  with the License.  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
# limitations under the License.
################################################################################
import unittest

from pyflink.table.expressions import col, call, lit, row_interval
from pyflink.table.types import DataTypes
from pyflink.table.udf import udaf, udf, AggregateFunction
from pyflink.testing import source_sink_utils
from pyflink.testing.test_case_utils import PyFlinkBatchTableTestCase, \
    PyFlinkStreamTableTestCase


class BatchPandasUDAFITTests(PyFlinkBatchTableTestCase):

    def test_check_result_type(self):
        def pandas_udaf():
            pass

        with self.assertRaises(
                TypeError,
                msg="Invalid returnType: Pandas UDAF doesn't support DataType type MAP currently"):
            udaf(pandas_udaf, result_type=DataTypes.MAP(DataTypes.INT(), DataTypes.INT()),
                 func_type="pandas")

    def test_group_aggregate_function(self):
        t = self.t_env.from_elements(
            [(1, 2, 3), (3, 2, 3), (2, 1, 3), (1, 5, 4), (1, 8, 6), (2, 3, 4)],
            DataTypes.ROW(
                [DataTypes.FIELD("a", DataTypes.TINYINT()),
                 DataTypes.FIELD("b", DataTypes.SMALLINT()),
                 DataTypes.FIELD("c", DataTypes.INT())]))

        table_sink = source_sink_utils.TestAppendSink(
            ['a', 'b', 'c'],
            [DataTypes.TINYINT(), DataTypes.FLOAT(),
             DataTypes.ROW(
                 [DataTypes.FIELD("a", DataTypes.INT()),
                  DataTypes.FIELD("b", DataTypes.INT())])])
        self.t_env.register_table_sink("Results", table_sink)
        # general udf
        add = udf(lambda a: a + 1, result_type=DataTypes.INT())
        # pandas udf
        substract = udf(lambda a: a - 1, result_type=DataTypes.INT(), func_type="pandas")
        max_udaf = udaf(lambda a: (a.max(), a.min()),
                        result_type=DataTypes.ROW(
                            [DataTypes.FIELD("a", DataTypes.INT()),
                             DataTypes.FIELD("b", DataTypes.INT())]),
                        func_type="pandas")
        t.group_by(t.a) \
            .select(t.a, mean_udaf(add(t.b)), max_udaf(substract(t.c))) \
            .execute_insert("Results") \
            .wait()
        actual = source_sink_utils.results()
        self.assert_equals(
            actual,
            ["+I[1, 6.0, +I[5, 2]]", "+I[2, 3.0, +I[3, 2]]", "+I[3, 3.0, +I[2, 2]]"])

    def test_group_aggregate_without_keys(self):
        t = self.t_env.from_elements(
            [(1, 2, 3), (3, 2, 3), (2, 1, 3), (1, 5, 4), (1, 8, 6), (2, 3, 4)],
            DataTypes.ROW(
                [DataTypes.FIELD("a", DataTypes.TINYINT()),
                 DataTypes.FIELD("b", DataTypes.SMALLINT()),
                 DataTypes.FIELD("c", DataTypes.INT())]))

        table_sink = source_sink_utils.TestAppendSink(
            ['a'],
            [DataTypes.INT()])
        min_add = udaf(lambda a, b, c: a.min() + b.min() + c.min(),
                       result_type=DataTypes.INT(), func_type="pandas")
        self.t_env.register_table_sink("Results", table_sink)
        t.select(min_add(t.a, t.b, t.c)) \
            .execute_insert("Results") \
            .wait()
        actual = source_sink_utils.results()
        self.assert_equals(actual, ["+I[5]"])

    def test_group_aggregate_with_aux_group(self):
        t = self.t_env.from_elements(
            [(1, 2, 3), (3, 2, 3), (2, 1, 3), (1, 5, 4), (1, 8, 6), (2, 3, 4)],
            DataTypes.ROW(
                [DataTypes.FIELD("a", DataTypes.TINYINT()),
                 DataTypes.FIELD("b", DataTypes.SMALLINT()),
                 DataTypes.FIELD("c", DataTypes.INT())]))

        table_sink = source_sink_utils.TestAppendSink(
            ['a', 'b', 'c', 'd'],
            [DataTypes.TINYINT(), DataTypes.INT(), DataTypes.FLOAT(), DataTypes.INT()])
        self.t_env.register_table_sink("Results", table_sink)
        self.t_env.get_config().get_configuration().set_string('python.metric.enabled', 'true')
        self.t_env.register_function("max_add", udaf(MaxAdd(),
                                                     result_type=DataTypes.INT(),
                                                     func_type="pandas"))
        self.t_env.create_temporary_system_function("mean_udaf", mean_udaf)
        t.group_by(t.a) \
            .select(t.a,  (t.a + 1).alias("b"), (t.a + 2).alias("c")) \
            .group_by(t.a, t.b) \
            .select(t.a, t.b, mean_udaf(t.b), call("max_add", t.b, t.c, 1)) \
            .execute_insert("Results") \
            .wait()
        actual = source_sink_utils.results()
        self.assert_equals(actual, ["+I[1, 2, 2.0, 6]", "+I[2, 3, 3.0, 8]", "+I[3, 4, 4.0, 10]"])

    def test_tumble_group_window_aggregate_function(self):
        import datetime
        from pyflink.table.window import Tumble
        t = self.t_env.from_elements(
            [
                (1, 2, 3, datetime.datetime(2018, 3, 11, 3, 10, 0, 0)),
                (3, 2, 4, datetime.datetime(2018, 3, 11, 3, 10, 0, 0)),
                (2, 1, 2, datetime.datetime(2018, 3, 11, 3, 10, 0, 0)),
                (1, 3, 1, datetime.datetime(2018, 3, 11, 3, 40, 0, 0)),
                (1, 8, 5, datetime.datetime(2018, 3, 11, 4, 20, 0, 0)),
                (2, 3, 6, datetime.datetime(2018, 3, 11, 3, 30, 0, 0))
            ],
            DataTypes.ROW(
                [DataTypes.FIELD("a", DataTypes.TINYINT()),
                 DataTypes.FIELD("b", DataTypes.SMALLINT()),
                 DataTypes.FIELD("c", DataTypes.INT()),
                 DataTypes.FIELD("rowtime", DataTypes.TIMESTAMP(3))]))

        table_sink = source_sink_utils.TestAppendSink(
            ['a', 'b', 'c'],
            [
                DataTypes.TIMESTAMP(3),
                DataTypes.TIMESTAMP(3),
                DataTypes.FLOAT()
            ])
        self.t_env.register_table_sink("Results", table_sink)
        self.t_env.create_temporary_system_function("mean_udaf", mean_udaf)
        tumble_window = Tumble.over(lit(1).hours) \
            .on(col("rowtime")) \
            .alias("w")
        t.window(tumble_window) \
            .group_by(col("w")) \
            .select(col("w").start, col("w").end, mean_udaf(t.b)) \
            .execute_insert("Results") \
            .wait()

        actual = source_sink_utils.results()
        self.assert_equals(actual,
                           ["+I[2018-03-11 03:00:00.0, 2018-03-11 04:00:00.0, 2.2]",
                            "+I[2018-03-11 04:00:00.0, 2018-03-11 05:00:00.0, 8.0]"])

    def test_slide_group_window_aggregate_function(self):
        import datetime
        from pyflink.table.window import Slide
        t = self.t_env.from_elements(
            [
                (1, 2, 3, datetime.datetime(2018, 3, 11, 3, 10, 0, 0)),
                (3, 2, 4, datetime.datetime(2018, 3, 11, 3, 10, 0, 0)),
                (2, 1, 2, datetime.datetime(2018, 3, 11, 3, 10, 0, 0)),
                (1, 3, 1, datetime.datetime(2018, 3, 11, 3, 40, 0, 0)),
                (1, 8, 5, datetime.datetime(2018, 3, 11, 4, 20, 0, 0)),
                (2, 3, 6, datetime.datetime(2018, 3, 11, 3, 30, 0, 0))
            ],
            DataTypes.ROW(
                [DataTypes.FIELD("a", DataTypes.TINYINT()),
                 DataTypes.FIELD("b", DataTypes.SMALLINT()),
                 DataTypes.FIELD("c", DataTypes.INT()),
                 DataTypes.FIELD("rowtime", DataTypes.TIMESTAMP(3))]))

        table_sink = source_sink_utils.TestAppendSink(
            ['a', 'b', 'c', 'd', 'e'],
            [
                DataTypes.TINYINT(),
                DataTypes.TIMESTAMP(3),
                DataTypes.TIMESTAMP(3),
                DataTypes.FLOAT(),
                DataTypes.INT()
            ])
        self.t_env.register_table_sink("Results", table_sink)
        self.t_env.register_function("max_add", udaf(MaxAdd(),
                                                     result_type=DataTypes.INT(),
                                                     func_type="pandas"))
        self.t_env.create_temporary_system_function("mean_udaf", mean_udaf)
        slide_window = Slide.over(lit(1).hours) \
            .every(lit(30).minutes) \
            .on(col("rowtime")) \
            .alias("w")
        t.window(slide_window) \
            .group_by(t.a, col("w")) \
            .select(t.a,
                    col("w").start,
                    col("w").end,
                    mean_udaf(t.b),
                    call("max_add", t.b, t.c, 1)) \
            .execute_insert("Results") \
            .wait()
        actual = source_sink_utils.results()
        self.assert_equals(actual,
                           ["+I[1, 2018-03-11 02:30:00.0, 2018-03-11 03:30:00.0, 2.0, 6]",
                            "+I[1, 2018-03-11 03:00:00.0, 2018-03-11 04:00:00.0, 2.5, 7]",
                            "+I[1, 2018-03-11 03:30:00.0, 2018-03-11 04:30:00.0, 5.5, 14]",
                            "+I[1, 2018-03-11 04:00:00.0, 2018-03-11 05:00:00.0, 8.0, 14]",
                            "+I[2, 2018-03-11 02:30:00.0, 2018-03-11 03:30:00.0, 1.0, 4]",
                            "+I[2, 2018-03-11 03:00:00.0, 2018-03-11 04:00:00.0, 2.0, 10]",
                            "+I[2, 2018-03-11 03:30:00.0, 2018-03-11 04:30:00.0, 3.0, 10]",
                            "+I[3, 2018-03-11 03:00:00.0, 2018-03-11 04:00:00.0, 2.0, 7]",
                            "+I[3, 2018-03-11 02:30:00.0, 2018-03-11 03:30:00.0, 2.0, 7]"])

    def test_over_window_aggregate_function(self):
        import datetime
        t = self.t_env.from_elements(
            [
                (1, 2, 3, datetime.datetime(2018, 3, 11, 3, 10, 0, 0)),
                (3, 2, 1, datetime.datetime(2018, 3, 11, 3, 10, 0, 0)),
                (2, 1, 2, datetime.datetime(2018, 3, 11, 3, 10, 0, 0)),
                (1, 3, 1, datetime.datetime(2018, 3, 11, 3, 10, 0, 0)),
                (1, 8, 5, datetime.datetime(2018, 3, 11, 4, 20, 0, 0)),
                (2, 3, 6, datetime.datetime(2018, 3, 11, 3, 30, 0, 0))
            ],
            DataTypes.ROW(
                [DataTypes.FIELD("a", DataTypes.TINYINT()),
                 DataTypes.FIELD("b", DataTypes.SMALLINT()),
                 DataTypes.FIELD("c", DataTypes.INT()),
                 DataTypes.FIELD("rowtime", DataTypes.TIMESTAMP(3))]))

        table_sink = source_sink_utils.TestAppendSink(
            ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j'],
            [DataTypes.TINYINT(), DataTypes.FLOAT(), DataTypes.INT(), DataTypes.FLOAT(),
             DataTypes.FLOAT(), DataTypes.FLOAT(), DataTypes.FLOAT(), DataTypes.FLOAT(),
             DataTypes.FLOAT(), DataTypes.FLOAT()])
        self.t_env.register_table_sink("Results", table_sink)
        self.t_env.create_temporary_system_function("mean_udaf", mean_udaf)
        self.t_env.register_function("max_add", udaf(MaxAdd(),
                                                     result_type=DataTypes.INT(),
                                                     func_type="pandas"))
        self.t_env.register_table("T", t)
        self.t_env.execute_sql("""
            insert into Results
            select a,
             mean_udaf(b)
             over (PARTITION BY a ORDER BY rowtime
             ROWS BETWEEN UNBOUNDED preceding AND UNBOUNDED FOLLOWING),
             max_add(b, c)
             over (PARTITION BY a ORDER BY rowtime
             ROWS BETWEEN UNBOUNDED preceding AND 0 FOLLOWING),
             mean_udaf(b)
             over (PARTITION BY a ORDER BY rowtime
             ROWS BETWEEN 1 PRECEDING AND UNBOUNDED FOLLOWING),
             mean_udaf(c)
             over (PARTITION BY a ORDER BY rowtime
             ROWS BETWEEN 1 PRECEDING AND 0 FOLLOWING),
             mean_udaf(c)
             over (PARTITION BY a ORDER BY rowtime
             RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING),
             mean_udaf(b)
             over (PARTITION BY a ORDER BY rowtime
             RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),
             mean_udaf(b)
             over (PARTITION BY a ORDER BY rowtime
             RANGE BETWEEN INTERVAL '20' MINUTE PRECEDING AND UNBOUNDED FOLLOWING),
             mean_udaf(c)
             over (PARTITION BY a ORDER BY rowtime
             RANGE BETWEEN INTERVAL '20' MINUTE PRECEDING AND UNBOUNDED FOLLOWING),
             mean_udaf(c)
             over (PARTITION BY a ORDER BY rowtime
             RANGE BETWEEN INTERVAL '20' MINUTE PRECEDING AND CURRENT ROW)
            from T
        """).wait()
        actual = source_sink_utils.results()
        self.assert_equals(actual,
                           ["+I[1, 4.3333335, 5, 4.3333335, 3.0, 3.0, 2.5, 4.3333335, 3.0, 2.0]",
                            "+I[1, 4.3333335, 13, 5.5, 3.0, 3.0, 4.3333335, 8.0, 5.0, 5.0]",
                            "+I[1, 4.3333335, 6, 4.3333335, 2.0, 3.0, 2.5, 4.3333335, 3.0, 2.0]",
                            "+I[2, 2.0, 9, 2.0, 4.0, 4.0, 2.0, 2.0, 4.0, 4.0]",
                            "+I[2, 2.0, 3, 2.0, 2.0, 4.0, 1.0, 2.0, 4.0, 2.0]",
                            "+I[3, 2.0, 3, 2.0, 1.0, 1.0, 2.0, 2.0, 1.0, 1.0]"])


class StreamPandasUDAFITTests(PyFlinkStreamTableTestCase):
    def test_sliding_group_window_over_time(self):
        # create source file path
        import tempfile
        import os
        tmp_dir = tempfile.gettempdir()
        data = [
            '1,1,2,2018-03-11 03:10:00',
            '3,3,2,2018-03-11 03:10:00',
            '2,2,1,2018-03-11 03:10:00',
            '1,1,3,2018-03-11 03:40:00',
            '1,1,8,2018-03-11 04:20:00',
            '2,2,3,2018-03-11 03:30:00'
        ]
        source_path = tmp_dir + '/test_sliding_group_window_over_time.csv'
        with open(source_path, 'w') as fd:
            for ele in data:
                fd.write(ele + '\n')

        from pyflink.table.window import Slide
        self.t_env.get_config().get_configuration().set_string(
            "pipeline.time-characteristic", "EventTime")
        self.t_env.register_function("mean_udaf", mean_udaf)

        source_table = """
            create table source_table(
                a TINYINT,
                b SMALLINT,
                c SMALLINT,
                rowtime TIMESTAMP(3),
                WATERMARK FOR rowtime AS rowtime - INTERVAL '60' MINUTE
            ) with(
                'connector.type' = 'filesystem',
                'format.type' = 'csv',
                'connector.path' = '%s',
                'format.ignore-first-line' = 'false',
                'format.field-delimiter' = ','
            )
        """ % source_path
        self.t_env.execute_sql(source_table)
        t = self.t_env.from_path("source_table")

        table_sink = source_sink_utils.TestAppendSink(
            ['a', 'b', 'c', 'd'],
            [
                DataTypes.TINYINT(),
                DataTypes.TIMESTAMP(3),
                DataTypes.TIMESTAMP(3),
                DataTypes.FLOAT()])
        self.t_env.register_table_sink("Results", table_sink)
        t.window(Slide.over(lit(1).hours)
                 .every(lit(30).minutes)
                 .on(col("rowtime"))
                 .alias("w")) \
            .group_by(t.a, t.b, col("w")) \
            .select(t.a, col("w").start, col("w").end, mean_udaf(t.c).alias("b")) \
            .execute_insert("Results") \
            .wait()
        actual = source_sink_utils.results()
        self.assert_equals(actual,
                           ["+I[1, 2018-03-11 02:30:00.0, 2018-03-11 03:30:00.0, 2.0]",
                            "+I[1, 2018-03-11 03:00:00.0, 2018-03-11 04:00:00.0, 2.5]",
                            "+I[1, 2018-03-11 03:30:00.0, 2018-03-11 04:30:00.0, 5.5]",
                            "+I[1, 2018-03-11 04:00:00.0, 2018-03-11 05:00:00.0, 8.0]",
                            "+I[2, 2018-03-11 02:30:00.0, 2018-03-11 03:30:00.0, 1.0]",
                            "+I[2, 2018-03-11 03:00:00.0, 2018-03-11 04:00:00.0, 2.0]",
                            "+I[2, 2018-03-11 03:30:00.0, 2018-03-11 04:30:00.0, 3.0]",
                            "+I[3, 2018-03-11 03:00:00.0, 2018-03-11 04:00:00.0, 2.0]",
                            "+I[3, 2018-03-11 02:30:00.0, 2018-03-11 03:30:00.0, 2.0]"])
        os.remove(source_path)

    def test_sliding_group_window_over_proctime(self):
        self.t_env.get_config().get_configuration().set_string("parallelism.default", "1")
        from pyflink.table.window import Slide
        self.t_env.register_function("mean_udaf", mean_udaf)

        source_table = """
            create table source_table(
                a INT,
                proctime as PROCTIME()
            ) with(
                'connector' = 'datagen',
                'rows-per-second' = '1',
                'fields.a.kind' = 'sequence',
                'fields.a.start' = '1',
                'fields.a.end' = '10'
            )
        """
        self.t_env.execute_sql(source_table)
        t = self.t_env.from_path("source_table")
        iterator = t.select(t.a, t.proctime) \
            .window(Slide.over(lit(1).seconds)
                    .every(lit(1).seconds)
                    .on(t.proctime)
                    .alias("w")) \
            .group_by(t.a, col("w")) \
            .select(mean_udaf(t.a).alias("b"), col("w").start).execute().collect()
        result = [i for i in iterator]
        # if the WindowAssigner.isEventTime() does not return false,
        # the w.start would be 1970-01-01
        # TODO: After fixing the TimeZone problem of window with processing time (will be fixed in
        # FLIP-162), we should replace it with a more accurate assertion.
        self.assertTrue(result[0][1].year > 1970)

    def test_sliding_group_window_over_count(self):
        self.t_env.get_config().get_configuration().set_string("parallelism.default", "1")
        # create source file path
        import tempfile
        import os
        tmp_dir = tempfile.gettempdir()
        data = [
            '1,1,2,2018-03-11 03:10:00',
            '3,3,2,2018-03-11 03:10:00',
            '2,2,1,2018-03-11 03:10:00',
            '1,1,3,2018-03-11 03:40:00',
            '1,1,8,2018-03-11 04:20:00',
            '2,2,3,2018-03-11 03:30:00',
            '3,3,3,2018-03-11 03:30:00'
        ]
        source_path = tmp_dir + '/test_sliding_group_window_over_count.csv'
        with open(source_path, 'w') as fd:
            for ele in data:
                fd.write(ele + '\n')

        from pyflink.table.window import Slide
        self.t_env.get_config().get_configuration().set_string(
            "pipeline.time-characteristic", "ProcessingTime")
        self.t_env.register_function("mean_udaf", mean_udaf)

        source_table = """
            create table source_table(
                a TINYINT,
                b SMALLINT,
                c SMALLINT,
                protime as PROCTIME()
            ) with(
                'connector.type' = 'filesystem',
                'format.type' = 'csv',
                'connector.path' = '%s',
                'format.ignore-first-line' = 'false',
                'format.field-delimiter' = ','
            )
        """ % source_path
        self.t_env.execute_sql(source_table)
        t = self.t_env.from_path("source_table")

        table_sink = source_sink_utils.TestAppendSink(
            ['a', 'd'],
            [
                DataTypes.TINYINT(),
                DataTypes.FLOAT()])
        self.t_env.register_table_sink("Results", table_sink)
        t.window(Slide.over(row_interval(2))
                 .every(row_interval(1))
                 .on(t.protime)
                 .alias("w")) \
            .group_by(t.a, t.b, col("w")) \
            .select(t.a, mean_udaf(t.c).alias("b")) \
            .execute_insert("Results") \
            .wait()
        actual = source_sink_utils.results()
        self.assert_equals(actual, ["+I[1, 2.5]", "+I[1, 5.5]", "+I[2, 2.0]", "+I[3, 2.5]"])
        os.remove(source_path)

    def test_tumbling_group_window_over_time(self):
        # create source file path
        import tempfile
        import os
        tmp_dir = tempfile.gettempdir()
        data = [
            '1,1,2,2018-03-11 03:10:00',
            '3,3,2,2018-03-11 03:10:00',
            '2,2,1,2018-03-11 03:10:00',
            '1,1,3,2018-03-11 03:40:00',
            '1,1,8,2018-03-11 04:20:00',
            '2,2,3,2018-03-11 03:30:00'
        ]
        source_path = tmp_dir + '/test_tumbling_group_window_over_time.csv'
        with open(source_path, 'w') as fd:
            for ele in data:
                fd.write(ele + '\n')

        from pyflink.table.window import Tumble
        self.t_env.get_config().get_configuration().set_string(
            "pipeline.time-characteristic", "EventTime")
        self.t_env.register_function("mean_udaf", mean_udaf)

        source_table = """
            create table source_table(
                a TINYINT,
                b SMALLINT,
                c SMALLINT,
                rowtime TIMESTAMP(3),
                WATERMARK FOR rowtime AS rowtime - INTERVAL '60' MINUTE
            ) with(
                'connector.type' = 'filesystem',
                'format.type' = 'csv',
                'connector.path' = '%s',
                'format.ignore-first-line' = 'false',
                'format.field-delimiter' = ','
            )
        """ % source_path
        self.t_env.execute_sql(source_table)
        t = self.t_env.from_path("source_table")

        table_sink = source_sink_utils.TestAppendSink(
            ['a', 'b', 'c', 'd', 'e'],
            [
                DataTypes.TINYINT(),
                DataTypes.TIMESTAMP(3),
                DataTypes.TIMESTAMP(3),
                DataTypes.TIMESTAMP(3),
                DataTypes.FLOAT()])
        self.t_env.register_table_sink("Results", table_sink)
        t.window(Tumble.over(lit(1).hours).on(t.rowtime).alias("w")) \
            .group_by(t.a, t.b, col("w")) \
            .select(t.a,
                    col("w").start,
                    col("w").end,
                    col("w").rowtime,
                    mean_udaf(t.c).alias("b")) \
            .execute_insert("Results") \
            .wait()
        actual = source_sink_utils.results()
        self.assert_equals(actual, [
            "+I[1, 2018-03-11 03:00:00.0, 2018-03-11 04:00:00.0, 2018-03-11 03:59:59.999, 2.5]",
            "+I[1, 2018-03-11 04:00:00.0, 2018-03-11 05:00:00.0, 2018-03-11 04:59:59.999, 8.0]",
            "+I[2, 2018-03-11 03:00:00.0, 2018-03-11 04:00:00.0, 2018-03-11 03:59:59.999, 2.0]",
            "+I[3, 2018-03-11 03:00:00.0, 2018-03-11 04:00:00.0, 2018-03-11 03:59:59.999, 2.0]",
        ])
        os.remove(source_path)

    def test_tumbling_group_window_over_count(self):
        self.t_env.get_config().get_configuration().set_string("parallelism.default", "1")
        # create source file path
        import tempfile
        import os
        tmp_dir = tempfile.gettempdir()
        data = [
            '1,1,2,2018-03-11 03:10:00',
            '3,3,2,2018-03-11 03:10:00',
            '2,2,1,2018-03-11 03:10:00',
            '1,1,3,2018-03-11 03:40:00',
            '1,1,8,2018-03-11 04:20:00',
            '2,2,3,2018-03-11 03:30:00',
            '3,3,3,2018-03-11 03:30:00',
            '1,1,4,2018-03-11 04:20:00',
        ]
        source_path = tmp_dir + '/test_group_window_aggregate_function_over_count.csv'
        with open(source_path, 'w') as fd:
            for ele in data:
                fd.write(ele + '\n')

        from pyflink.table.window import Tumble
        self.t_env.get_config().get_configuration().set_string(
            "pipeline.time-characteristic", "ProcessingTime")
        self.t_env.register_function("mean_udaf", mean_udaf)

        source_table = """
            create table source_table(
                a TINYINT,
                b SMALLINT,
                c SMALLINT,
                protime as PROCTIME()
            ) with(
                'connector.type' = 'filesystem',
                'format.type' = 'csv',
                'connector.path' = '%s',
                'format.ignore-first-line' = 'false',
                'format.field-delimiter' = ','
            )
        """ % source_path
        self.t_env.execute_sql(source_table)
        t = self.t_env.from_path("source_table")

        table_sink = source_sink_utils.TestAppendSink(
            ['a', 'd'],
            [
                DataTypes.TINYINT(),
                DataTypes.FLOAT()])
        self.t_env.register_table_sink("Results", table_sink)
        t.window(Tumble.over(row_interval(2)).on(t.protime).alias("w")) \
            .group_by(t.a, t.b, col("w")) \
            .select(t.a, mean_udaf(t.c).alias("b")) \
            .execute_insert("Results") \
            .wait()
        actual = source_sink_utils.results()
        self.assert_equals(actual, ["+I[1, 2.5]", "+I[1, 6.0]", "+I[2, 2.0]", "+I[3, 2.5]"])
        os.remove(source_path)

    def test_row_time_over_range_window_aggregate_function(self):
        # create source file path
        import tempfile
        import os
        tmp_dir = tempfile.gettempdir()
        data = [
            '1,1,2013-01-01 03:10:00',
            '3,2,2013-01-01 03:10:00',
            '2,1,2013-01-01 03:10:00',
            '1,5,2013-01-01 03:10:00',
            '1,8,2013-01-01 04:20:00',
            '2,3,2013-01-01 03:30:00'
        ]
        source_path = tmp_dir + '/test_over_range_window_aggregate_function.csv'
        with open(source_path, 'w') as fd:
            for ele in data:
                fd.write(ele + '\n')
        max_add_min_udaf = udaf(lambda a: a.max() + a.min(),
                                result_type=DataTypes.SMALLINT(),
                                func_type='pandas')
        self.t_env.get_config().get_configuration().set_string(
            "pipeline.time-characteristic", "EventTime")
        self.t_env.register_function("mean_udaf", mean_udaf)
        self.t_env.register_function("max_add_min_udaf", max_add_min_udaf)
        source_table = """
            create table source_table(
                a TINYINT,
                b SMALLINT,
                rowtime TIMESTAMP(3),
                WATERMARK FOR rowtime AS rowtime - INTERVAL '60' MINUTE
            ) with(
                'connector.type' = 'filesystem',
                'format.type' = 'csv',
                'connector.path' = '%s',
                'format.ignore-first-line' = 'false',
                'format.field-delimiter' = ','
            )
        """ % source_path
        self.t_env.execute_sql(source_table)
        table_sink = source_sink_utils.TestAppendSink(
            ['a', 'b', 'c'],
            [
                DataTypes.TINYINT(),
                DataTypes.FLOAT(),
                DataTypes.SMALLINT()])
        self.t_env.register_table_sink("Results", table_sink)
        self.t_env.execute_sql("""
            insert into Results
            select a,
             mean_udaf(b)
             over (PARTITION BY a ORDER BY rowtime
             RANGE BETWEEN INTERVAL '20' MINUTE PRECEDING AND CURRENT ROW),
             max_add_min_udaf(b)
             over (PARTITION BY a ORDER BY rowtime
             RANGE BETWEEN INTERVAL '20' MINUTE PRECEDING AND CURRENT ROW)
            from source_table
        """).wait()
        actual = source_sink_utils.results()
        self.assert_equals(actual,
                           ["+I[1, 3.0, 6]",
                            "+I[1, 3.0, 6]",
                            "+I[1, 8.0, 16]",
                            "+I[2, 1.0, 2]",
                            "+I[2, 2.0, 4]",
                            "+I[3, 2.0, 4]"])
        os.remove(source_path)

    def test_row_time_over_rows_window_aggregate_function(self):
        # create source file path
        import tempfile
        import os
        tmp_dir = tempfile.gettempdir()
        data = [
            '1,1,2013-01-01 03:10:00',
            '3,2,2013-01-01 03:10:00',
            '2,1,2013-01-01 03:10:00',
            '1,5,2013-01-01 03:10:00',
            '1,8,2013-01-01 04:20:00',
            '2,3,2013-01-01 03:30:00'
        ]
        source_path = tmp_dir + '/test_over_rows_window_aggregate_function.csv'
        with open(source_path, 'w') as fd:
            for ele in data:
                fd.write(ele + '\n')

        max_add_min_udaf = udaf(lambda a: a.max() + a.min(),
                                result_type=DataTypes.SMALLINT(),
                                func_type='pandas')
        self.t_env.get_config().get_configuration().set_string(
            "pipeline.time-characteristic", "EventTime")
        self.t_env.register_function("mean_udaf", mean_udaf)
        self.t_env.register_function("max_add_min_udaf", max_add_min_udaf)
        source_table = """
            create table source_table(
                a TINYINT,
                b SMALLINT,
                rowtime TIMESTAMP(3),
                WATERMARK FOR rowtime AS rowtime - INTERVAL '60' MINUTE
            ) with(
                'connector.type' = 'filesystem',
                'format.type' = 'csv',
                'connector.path' = '%s',
                'format.ignore-first-line' = 'false',
                'format.field-delimiter' = ','
            )
        """ % source_path
        self.t_env.execute_sql(source_table)
        table_sink = source_sink_utils.TestAppendSink(
            ['a', 'b', 'c'],
            [
                DataTypes.TINYINT(),
                DataTypes.FLOAT(),
                DataTypes.SMALLINT()])
        self.t_env.register_table_sink("Results", table_sink)
        self.t_env.execute_sql("""
            insert into Results
            select a,
             mean_udaf(b)
             over (PARTITION BY a ORDER BY rowtime
             ROWS BETWEEN 1 PRECEDING AND CURRENT ROW),
             max_add_min_udaf(b)
             over (PARTITION BY a ORDER BY rowtime
             ROWS BETWEEN 1 PRECEDING AND CURRENT ROW)
            from source_table
        """).wait()
        actual = source_sink_utils.results()
        self.assert_equals(actual,
                           ["+I[1, 1.0, 2]",
                            "+I[1, 3.0, 6]",
                            "+I[1, 6.5, 13]",
                            "+I[2, 1.0, 2]",
                            "+I[2, 2.0, 4]",
                            "+I[3, 2.0, 4]"])
        os.remove(source_path)

    def test_proc_time_over_rows_window_aggregate_function(self):
        # create source file path
        import tempfile
        import os
        tmp_dir = tempfile.gettempdir()
        data = [
            '1,1,2013-01-01 03:10:00',
            '3,2,2013-01-01 03:10:00',
            '2,1,2013-01-01 03:10:00',
            '1,5,2013-01-01 03:10:00',
            '1,8,2013-01-01 04:20:00',
            '2,3,2013-01-01 03:30:00'
        ]
        source_path = tmp_dir + '/test_over_rows_window_aggregate_function.csv'
        with open(source_path, 'w') as fd:
            for ele in data:
                fd.write(ele + '\n')

        max_add_min_udaf = udaf(lambda a: a.max() + a.min(),
                                result_type=DataTypes.SMALLINT(),
                                func_type='pandas')
        self.t_env.get_config().get_configuration().set_string("parallelism.default", "1")
        self.t_env.get_config().get_configuration().set_string(
            "pipeline.time-characteristic", "ProcessingTime")
        self.t_env.register_function("mean_udaf", mean_udaf)
        self.t_env.register_function("max_add_min_udaf", max_add_min_udaf)
        source_table = """
            create table source_table(
                a TINYINT,
                b SMALLINT,
                proctime as PROCTIME()
            ) with(
                'connector.type' = 'filesystem',
                'format.type' = 'csv',
                'connector.path' = '%s',
                'format.ignore-first-line' = 'false',
                'format.field-delimiter' = ','
            )
        """ % source_path
        self.t_env.execute_sql(source_table)
        table_sink = source_sink_utils.TestAppendSink(
            ['a', 'b', 'c'],
            [
                DataTypes.TINYINT(),
                DataTypes.FLOAT(),
                DataTypes.SMALLINT()])
        self.t_env.register_table_sink("Results", table_sink)
        self.t_env.execute_sql("""
            insert into Results
            select a,
             mean_udaf(b)
             over (PARTITION BY a ORDER BY proctime
             ROWS BETWEEN 1 PRECEDING AND CURRENT ROW),
             max_add_min_udaf(b)
             over (PARTITION BY a ORDER BY proctime
             ROWS BETWEEN 1 PRECEDING AND CURRENT ROW)
            from source_table
        """).wait()
        actual = source_sink_utils.results()
        self.assert_equals(actual,
                           ["+I[1, 1.0, 2]",
                            "+I[1, 3.0, 6]",
                            "+I[1, 6.5, 13]",
                            "+I[2, 1.0, 2]",
                            "+I[2, 2.0, 4]",
                            "+I[3, 2.0, 4]"])
        os.remove(source_path)

    @unittest.skip("Python UDFs are currently unsupported in JSON plan")
    def test_execute_over_aggregate_from_json_plan(self):
        # create source file path
        tmp_dir = self.tempdir
        data = [
            '1,1,2013-01-01 03:10:00',
            '3,2,2013-01-01 03:10:00',
            '2,1,2013-01-01 03:10:00',
            '1,5,2013-01-01 03:10:00',
            '1,8,2013-01-01 04:20:00',
            '2,3,2013-01-01 03:30:00'
        ]
        source_path = tmp_dir + '/test_execute_over_aggregate_from_json_plan.csv'
        sink_path = tmp_dir + '/test_execute_over_aggregate_from_json_plan'
        with open(source_path, 'w') as fd:
            for ele in data:
                fd.write(ele + '\n')

        source_table = """
            CREATE TABLE source_table (
                a TINYINT,
                b SMALLINT,
                rowtime TIMESTAMP(3),
                WATERMARK FOR rowtime AS rowtime - INTERVAL '60' MINUTE
            ) WITH (
                'connector' = 'filesystem',
                'path' = '%s',
                'format' = 'csv'
            )
        """ % source_path
        self.t_env.execute_sql(source_table)

        self.t_env.execute_sql("""
            CREATE TABLE sink_table (
                a TINYINT,
                b FLOAT,
                c SMALLINT
            ) WITH (
                'connector' = 'filesystem',
                'path' = '%s',
                'format' = 'csv'
            )
        """ % sink_path)

        max_add_min_udaf = udaf(lambda a: a.max() + a.min(),
                                result_type=DataTypes.SMALLINT(),
                                func_type='pandas')
        self.t_env.get_config().get_configuration().set_string(
            "pipeline.time-characteristic", "EventTime")
        self.t_env.create_temporary_system_function("mean_udaf", mean_udaf)
        self.t_env.create_temporary_system_function("max_add_min_udaf", max_add_min_udaf)

        json_plan = self.t_env._j_tenv.compilePlanSql("""
        insert into sink_table
            select a,
             mean_udaf(b)
             over (PARTITION BY a ORDER BY rowtime
             ROWS BETWEEN 1 PRECEDING AND CURRENT ROW),
             max_add_min_udaf(b)
             over (PARTITION BY a ORDER BY rowtime
             ROWS BETWEEN 1 PRECEDING AND CURRENT ROW)
            from source_table
        """)
        from py4j.java_gateway import get_method
        get_method(self.t_env._j_tenv.executePlan(json_plan), "await")()

        import glob
        lines = [line.strip() for file in glob.glob(sink_path + '/*') for line in open(file, 'r')]
        lines.sort()
        self.assertEqual(lines, ['1,1.0,2', '1,3.0,6', '1,6.5,13', '2,1.0,2', '2,2.0,4', '3,2.0,4'])


@udaf(result_type=DataTypes.FLOAT(), func_type="pandas")
def mean_udaf(v):
    return v.mean()


class MaxAdd(AggregateFunction, unittest.TestCase):

    def open(self, function_context):
        mg = function_context.get_metric_group()
        self.counter = mg.add_group("key", "value").counter("my_counter")
        self.counter_sum = 0

    def get_value(self, accumulator):
        # counter
        self.counter.inc(10)
        self.counter_sum += 10
        return accumulator[0]

    def create_accumulator(self):
        return []

    def accumulate(self, accumulator, *args):
        result = 0
        for arg in args:
            result += arg.max()
        accumulator.append(result)


if __name__ == '__main__':
    import unittest

    try:
        import xmlrunner

        testRunner = xmlrunner.XMLTestRunner(output='target/test-reports')
    except ImportError:
        testRunner = None
    unittest.main(testRunner=testRunner, verbosity=2)
