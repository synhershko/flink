/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package org.apache.flink.table.planner.expressions.converter;

import org.apache.flink.table.api.DataTypes;
import org.apache.flink.table.api.TableConfig;
import org.apache.flink.table.catalog.CatalogManager;
import org.apache.flink.table.catalog.FunctionCatalog;
import org.apache.flink.table.expressions.TimePointUnit;
import org.apache.flink.table.module.ModuleManager;
import org.apache.flink.table.planner.delegation.PlannerContext;
import org.apache.flink.table.planner.plan.metadata.MetadataTestUtil;
import org.apache.flink.table.planner.plan.trait.FlinkRelDistributionTraitDef;
import org.apache.flink.table.utils.CatalogManagerMocks;

import org.apache.calcite.avatica.util.TimeUnit;
import org.apache.calcite.jdbc.CalciteSchema;
import org.apache.calcite.plan.ConventionTraitDef;
import org.apache.calcite.rel.RelCollationTraitDef;
import org.apache.calcite.rex.RexLiteral;
import org.apache.calcite.rex.RexNode;
import org.apache.calcite.sql.type.SqlTypeName;
import org.apache.calcite.util.DateString;
import org.apache.calcite.util.TimeString;
import org.apache.calcite.util.TimestampString;
import org.junit.Test;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.Period;
import java.util.Arrays;

import static org.apache.flink.table.expressions.ApiExpressionUtils.valueLiteral;
import static org.assertj.core.api.Assertions.assertThat;

/** Test for {@link ExpressionConverter}. */
public class ExpressionConverterTest {

    private final TableConfig tableConfig = TableConfig.getDefault();
    private final CatalogManager catalogManager = CatalogManagerMocks.createEmptyCatalogManager();
    private final ModuleManager moduleManager = new ModuleManager();
    private final PlannerContext plannerContext =
            new PlannerContext(
                    false,
                    tableConfig,
                    moduleManager,
                    new FunctionCatalog(tableConfig, catalogManager, moduleManager),
                    catalogManager,
                    CalciteSchema.from(MetadataTestUtil.initRootSchema()),
                    Arrays.asList(
                            ConventionTraitDef.INSTANCE,
                            FlinkRelDistributionTraitDef.INSTANCE(),
                            RelCollationTraitDef.INSTANCE));
    private final ExpressionConverter converter =
            new ExpressionConverter(
                    plannerContext.createRelBuilder(
                            CatalogManagerMocks.DEFAULT_CATALOG,
                            CatalogManagerMocks.DEFAULT_DATABASE));

    @Test
    public void testLiteral() {
        RexNode rex = converter.visit(valueLiteral((byte) 1));
        assertThat((int) ((RexLiteral) rex).getValueAs(Integer.class)).isEqualTo(1);
        assertThat(rex.getType().getSqlTypeName()).isEqualTo(SqlTypeName.TINYINT);

        rex = converter.visit(valueLiteral((short) 1));
        assertThat((int) ((RexLiteral) rex).getValueAs(Integer.class)).isEqualTo(1);
        assertThat(rex.getType().getSqlTypeName()).isEqualTo(SqlTypeName.SMALLINT);

        rex = converter.visit(valueLiteral(1));
        assertThat((int) ((RexLiteral) rex).getValueAs(Integer.class)).isEqualTo(1);
        assertThat(rex.getType().getSqlTypeName()).isEqualTo(SqlTypeName.INTEGER);
    }

    @Test
    public void testCharLiteral() {
        RexNode rex = converter.visit(valueLiteral("ABC", DataTypes.CHAR(4).notNull()));
        assertThat(((RexLiteral) rex).getValueAs(String.class)).isEqualTo("ABC ");
        assertThat(rex.getType().getSqlTypeName()).isEqualTo(SqlTypeName.CHAR);
        assertThat(rex.getType().getPrecision()).isEqualTo(4);
    }

    @Test
    public void testVarCharLiteral() {
        RexNode rex = converter.visit(valueLiteral("ABC", DataTypes.STRING().notNull()));
        assertThat(((RexLiteral) rex).getValueAs(String.class)).isEqualTo("ABC");
        assertThat(rex.getType().getSqlTypeName()).isEqualTo(SqlTypeName.VARCHAR);
        assertThat(rex.getType().getPrecision()).isEqualTo(Integer.MAX_VALUE);
    }

    @Test
    public void testBinaryLiteral() {
        RexNode rex =
                converter.visit(valueLiteral(new byte[] {1, 2, 3}, DataTypes.BINARY(4).notNull()));
        assertThat(((RexLiteral) rex).getValueAs(byte[].class)).isEqualTo(new byte[] {1, 2, 3, 0});
        assertThat(rex.getType().getSqlTypeName()).isEqualTo(SqlTypeName.BINARY);
        assertThat(rex.getType().getPrecision()).isEqualTo(4);
    }

    @Test
    public void testTimestampLiteral() {
        RexNode rex =
                converter.visit(
                        valueLiteral(
                                LocalDateTime.parse("2012-12-12T12:12:12.12345"),
                                DataTypes.TIMESTAMP(3).notNull()));
        assertThat(((RexLiteral) rex).getValueAs(TimestampString.class))
                .isEqualTo(new TimestampString("2012-12-12 12:12:12.123"));
        assertThat(rex.getType().getSqlTypeName()).isEqualTo(SqlTypeName.TIMESTAMP);
        assertThat(rex.getType().getPrecision()).isEqualTo(3);
    }

    @Test
    public void testTimestampWithLocalZoneLiteral() {
        RexNode rex =
                converter.visit(
                        valueLiteral(
                                Instant.ofEpochMilli(100),
                                DataTypes.TIMESTAMP_WITH_LOCAL_TIME_ZONE(3).notNull()));
        assertThat(((RexLiteral) rex).getValueAs(TimestampString.class))
                .isEqualTo(TimestampString.fromMillisSinceEpoch(100));
        assertThat(rex.getType().getSqlTypeName())
                .isEqualTo(SqlTypeName.TIMESTAMP_WITH_LOCAL_TIME_ZONE);
        assertThat(rex.getType().getPrecision()).isEqualTo(3);
    }

    @Test
    public void testTimeLiteral() {
        RexNode rex =
                converter.visit(
                        valueLiteral(
                                LocalTime.parse("12:12:12.12345"), DataTypes.TIME(2).notNull()));
        assertThat(((RexLiteral) rex).getValueAs(TimeString.class))
                .isEqualTo(new TimeString("12:12:12.12"));
        assertThat(rex.getType().getSqlTypeName()).isEqualTo(SqlTypeName.TIME);
        assertThat(rex.getType().getPrecision()).isEqualTo(2);
    }

    @Test
    public void testTimeLiteralBiggerPrecision() {
        RexNode rex =
                converter.visit(
                        valueLiteral(
                                LocalTime.parse("12:12:12.12345"), DataTypes.TIME(5).notNull()));
        // TODO planner supports up to TIME(3)
        assertThat(((RexLiteral) rex).getValueAs(TimeString.class))
                .isEqualTo(new TimeString("12:12:12.123"));
        assertThat(rex.getType().getSqlTypeName()).isEqualTo(SqlTypeName.TIME);
        assertThat(rex.getType().getPrecision()).isEqualTo(3);
    }

    @Test
    public void testDateLiteral() {
        RexNode rex =
                converter.visit(
                        valueLiteral(LocalDate.parse("2012-12-12"), DataTypes.DATE().notNull()));
        assertThat(((RexLiteral) rex).getValueAs(DateString.class))
                .isEqualTo(new DateString("2012-12-12"));
        assertThat(rex.getType().getSqlTypeName()).isEqualTo(SqlTypeName.DATE);
    }

    @Test
    public void testIntervalDayTime() {
        Duration value = Duration.ofDays(3).plusMillis(21);
        RexNode rex = converter.visit(valueLiteral(value));
        assertThat(((RexLiteral) rex).getValueAs(BigDecimal.class))
                .isEqualTo(BigDecimal.valueOf(value.toMillis()));
        assertThat(rex.getType().getSqlTypeName()).isEqualTo(SqlTypeName.INTERVAL_DAY_SECOND);
        // TODO planner ignores the precision
        assertThat(rex.getType().getPrecision())
                .isEqualTo(2); // day precision, should actually be 1
        assertThat(rex.getType().getScale())
                .isEqualTo(6); // fractional precision, should actually be 3
    }

    @Test
    public void testIntervalYearMonth() {
        Period value = Period.of(999, 3, 1);
        RexNode rex = converter.visit(valueLiteral(value));
        assertThat(((RexLiteral) rex).getValueAs(BigDecimal.class))
                .isEqualTo(BigDecimal.valueOf(value.toTotalMonths()));
        // TODO planner ignores the precision
        assertThat(rex.getType().getSqlTypeName()).isEqualTo(SqlTypeName.INTERVAL_YEAR_MONTH);
        assertThat(rex.getType().getPrecision())
                .isEqualTo(2); // year precision, should actually be 3
    }

    @Test
    public void testDecimalLiteral() {
        BigDecimal value = new BigDecimal("12345678.999");
        RexNode rex = converter.visit(valueLiteral(value));
        assertThat(((RexLiteral) rex).getValueAs(BigDecimal.class)).isEqualTo(value);
        assertThat(rex.getType().getSqlTypeName()).isEqualTo(SqlTypeName.DECIMAL);
        assertThat(rex.getType().getPrecision()).isEqualTo(11);
        assertThat(rex.getType().getScale()).isEqualTo(3);
    }

    @Test
    public void testSymbolLiteral() {
        RexNode rex = converter.visit(valueLiteral(TimePointUnit.MICROSECOND));
        assertThat(((RexLiteral) rex).getValueAs(TimeUnit.class)).isEqualTo(TimeUnit.MICROSECOND);
        assertThat(rex.getType().getSqlTypeName()).isEqualTo(SqlTypeName.SYMBOL);
    }
}
