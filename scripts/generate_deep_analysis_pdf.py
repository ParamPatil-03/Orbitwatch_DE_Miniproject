"""
ORBITWATCH – scripts/generate_deep_analysis_pdf.py
Generates a comprehensive, publication-grade Deep Analysis PDF Report
covering the entire architecture, front-end, back-end, data pipelines,
database schemas, data quality, and physical space domain findings.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PDF = ROOT / "docs" / "ORBITWATCH_Deep_Analysis_Report.pdf"


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically compute and draw total page numbers and headers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))

        # Do not draw running header on cover page
        if self._pageNumber > 1:
            self.drawString(
                54,
                750,
                "ORBITWATCH: Comprehensive Technical Architecture & Deep Analysis Report",
            )
            self.setStrokeColor(colors.HexColor("#E2E8F0"))
            self.setLineWidth(0.5)
            self.line(54, 742, 558, 742)

            # Footer
            page_text = f"Page {self._pageNumber} of {page_count}"
            self.drawRightString(558, 36, page_text)
            self.drawString(
                54,
                36,
                "Confidential — Academic & Technical Evaluation Document",
            )
            self.line(54, 48, 558, 48)

        self.restoreState()


def create_deep_analysis_pdf():
    OUTPUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT_PDF),
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54,
    )

    styles = getSampleStyleSheet()

    # Custom Color Palette
    PRIMARY = colors.HexColor("#0F172A")    # Deep Navy
    SECONDARY = colors.HexColor("#1E3A8A")  # Royal Slate Blue
    ACCENT = colors.HexColor("#2563EB")     # Bright Blue
    TEXT_DARK = colors.HexColor("#1E293B")  # Charcoal body
    MUTED = colors.HexColor("#64748B")      # Muted slate
    BG_LIGHT = colors.HexColor("#F8FAFC")   # Light background
    BORDER_COL = colors.HexColor("#CBD5E1")

    # Typography Styles
    title_style = ParagraphStyle(
        "CoverTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=30,
        textColor=PRIMARY,
        spaceAfter=8,
    )
    subtitle_style = ParagraphStyle(
        "CoverSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=12,
        leading=16,
        textColor=MUTED,
        spaceAfter=20,
    )
    h1_style = ParagraphStyle(
        "Heading1_Custom",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=19,
        textColor=PRIMARY,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True,
    )
    h2_style = ParagraphStyle(
        "Heading2_Custom",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=SECONDARY,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True,
    )
    body_style = ParagraphStyle(
        "Body_Custom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=TEXT_DARK,
        spaceAfter=6,
    )
    bullet_style = ParagraphStyle(
        "Bullet_Custom",
        parent=body_style,
        leftIndent=15,
        firstLineIndent=-10,
        spaceAfter=3,
    )
    callout_style = ParagraphStyle(
        "Callout",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#92400E"),
        spaceBefore=4,
        spaceAfter=4,
    )
    th_style = ParagraphStyle(
        "TH",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.white,
    )
    td_style = ParagraphStyle(
        "TD",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9.5,
        textColor=TEXT_DARK,
    )

    story = []

    # ══════════════════════════════════════════════════════════════════════════
    # 1. COVER PAGE / HEADER
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("ORBITWATCH PLATFORM", title_style))
    story.append(
        Paragraph(
            "Space Domain Awareness, Solar Weather Telemetry & Atmospheric Drag Analytics<br/>"
            "<b>Comprehensive Architectural & Engineering Deep Analysis</b>",
            subtitle_style,
        )
    )
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=14))

    meta_table_data = [
        [
            Paragraph("<b>Project Version:</b> Production 1.0 (Phases 1-10)", td_style),
            Paragraph("<b>Primary Platform:</b> Windows 11 / Linux (Docker Engine)", td_style),
        ],
        [
            Paragraph("<b>Author / Engineer:</b> Param Patil", td_style),
            Paragraph(f"<b>Generated:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", td_style),
        ],
        [
            Paragraph("<b>Repository:</b> ParamPatil-03/Orbitwatch_DE_Miniproject", td_style),
            Paragraph("<b>Status:</b> Fully Verified (43 Automated Tests Passing)", td_style),
        ],
    ]
    meta_table = Table(meta_table_data, colWidths=[250, 250])
    meta_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BG_LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER_COL),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ])
    )
    story.append(meta_table)
    story.append(Spacer(1, 14))

    # ══════════════════════════════════════════════════════════════════════════
    # 2. EXECUTIVE SUMMARY & PROBLEM STATEMENT
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("1. Executive Summary & Problem Statement", h1_style))
    story.append(
        Paragraph(
            "The rapid proliferation of commercial satellite mega-constellations (e.g., Starlink, OneWeb) "
            "and historical fragmentation debris has created an acute congestion crisis in Low Earth Orbit (LEO). "
            "Predicting satellite collision avoidance and atmospheric re-entry requires modeling the interaction between "
            "orbital mechanics and upper atmospheric drag. Atmospheric drag in LEO (200–600 km) is fundamentally driven by "
            "solar activity: Extreme Ultraviolet (EUV) radiation expands Earth's thermosphere, multiplying neutral density "
            "by up to an order of magnitude and accelerating orbital decay.",
            body_style,
        )
    )
    story.append(
        Paragraph(
            "<b>ORBITWATCH</b> solves this domain problem by establishing an end-to-end, multi-tier data engineering platform. "
            "It ingests continuous satellite ephemerides from <b>CelesTrak</b> alongside multi-decade solar radio flux (F10.7) "
            "and sunspot indices from <b>NOAA SWPC</b>. The platform coordinates polyglot ingestion, event-driven CDC streaming, "
            "automated data quality gates, Kimball dimensional star schemas, Lakehouse exports, workflow orchestration, and "
            "role-governed executive visualization.",
            body_style,
        )
    )
    story.append(Spacer(1, 10))

    # ══════════════════════════════════════════════════════════════════════════
    # 3. END-TO-END ARCHITECTURE SPECIFICATION
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("2. Full Architectural Topology & Tech Stack", h1_style))
    story.append(
        Paragraph(
            "The platform leverages a polyglot persistence architecture designed for high availability, ACID reliability, "
            "and high-throughput analytical scans:",
            body_style,
        )
    )

    arch_table_data = [
        [Paragraph("Layer", th_style), Paragraph("Component", th_style), Paragraph("Technology", th_style), Paragraph("Technical Role & Description", th_style)],
        [Paragraph("Ingestion", td_style), Paragraph("REST Microservice", td_style), Paragraph("FastAPI + Uvicorn", td_style), Paragraph("Async HTTP ingestion of raw external payloads with API auth.", td_style)],
        [Paragraph("Raw Store", td_style), Paragraph("Document Database", td_style), Paragraph("MongoDB 7.0", td_style), Paragraph("NoSQL store with composite keys for idempotent raw archiving.", td_style)],
        [Paragraph("Streaming", td_style), Paragraph("Event Broker", td_style), Paragraph("Redpanda (Kafka API)", td_style), Paragraph("Low-latency C++ event broker streaming CDC topics (:19092).", td_style)],
        [Paragraph("Staging", td_style), Paragraph("Relational Staging", td_style), Paragraph("PostgreSQL 16", td_style), Paragraph("Landing area for raw consumed payloads (staging.*_raw).", td_style)],
        [Paragraph("Quality", td_style), Paragraph("Validation Engine", td_style), Paragraph("Great Expectations 1.x", td_style), Paragraph("Two-tier validation, dead-letter routing, and HTML docs.", td_style)],
        [Paragraph("Warehouse", td_style), Paragraph("Dimensional Schema", td_style), Paragraph("PostgreSQL schema 'dw'", td_style), Paragraph("Kimball star schema with surrogate keys and strict FKs.", td_style)],
        [Paragraph("Lakehouse", td_style), Paragraph("Columnar Lake", td_style), Paragraph("Delta Lake + DuckDB", td_style), Paragraph("ACID Parquet tables in data/lake/ queried via DuckDB.", td_style)],
        [Paragraph("Orchestration", td_style), Paragraph("Workflow DAG", td_style), Paragraph("Prefect 3.8", td_style), Paragraph("Sequential task execution with retries and failure gates.", td_style)],
        [Paragraph("Serving", td_style), Paragraph("Executive Dashboard", td_style), Paragraph("Streamlit 1.65", td_style), Paragraph("Role-governed visualizer (dashboard_user) with drag analysis.", td_style)],
    ]
    arch_table = Table(arch_table_data, colWidths=[65, 85, 105, 245])
    arch_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), SECONDARY),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COL),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ])
    )
    story.append(arch_table)
    story.append(Spacer(1, 14))

    # ══════════════════════════════════════════════════════════════════════════
    # 4. INGESTION, STREAMING & CHANGE DATA CAPTURE
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("3. Ingestion & Event-Driven Streaming Pipeline", h1_style))
    story.append(
        Paragraph(
            "<b>Ingestion Layer:</b> External telemetry sources (CelesTrak SATCAT and General Perturbations orbital elements; "
            "NOAA SWPC Solar Cycles and Planetary K-indices) are collected via HTTP scrapers. The raw JSON and CSV data streams "
            "into a FastAPI service (<code>/ingest/{source}</code>), which writes directly to MongoDB collections: "
            "<code>raw_gp</code>, <code>raw_satcat</code>, <code>raw_solar</code>, and <code>raw_k_index</code>. "
            "Idempotency is enforced at the MongoDB layer using unique compound indexes on natural composite keys "
            "(e.g., <code>norad_cat_id + epoch</code>), guaranteeing zero duplicate writes upon re-scraping.",
            body_style,
        )
    )
    story.append(
        Paragraph(
            "<b>Event Streaming (CDC):</b> The MongoDB collection states are monitored by a Kafka producer "
            "(<code>src/orbitwatch/streaming/producer.py</code>) that converts documents into standardized JSON message envelopes. "
            "Each message contains a deterministic UUID5 event ID derived from the natural key. Events are published to Redpanda "
            "topics: <code>orbitwatch.gp</code>, <code>orbitwatch.k_index</code>, and <code>orbitwatch.solar_indices</code>. "
            "A dedicated consumer (<code>consumer.py</code>) reads the streams, verifies payload integrity, and inserts valid records "
            "into PostgreSQL staging tables (<code>staging.*_raw</code>). Malformed payloads or invalid envelopes are intercepted "
            "and routed directly into <code>quality.dead_letter</code>.",
            body_style,
        )
    )
    story.append(Spacer(1, 10))

    # ══════════════════════════════════════════════════════════════════════════
    # 5. DATA QUALITY & GREAT EXPECTATIONS SUITES
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("4. Data Quality Gates, Validation & Governance", h1_style))
    story.append(
        Paragraph(
            "The platform implements a stringent two-tier quality gate using <b>Great Expectations 1.x</b> "
            "before any data is admitted into clean staging or warehouse layers:",
            body_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Tier 1 (Raw Suites):</b> Evaluates raw consumed records. Validates physical orbital parameter limits: "
            "inclination $0 \le i \le 180^\circ$, eccentricity $0 \le e < 1.0$ (parabolic/hyperbolic orbits rejected), "
            "mean motion $n > 0$ rev/day, and chronological validity (epoch cannot be in the future relative to UTC execution time).",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Tier 2 (Clean Suites):</b> Evaluates relational referential integrity. Ensures valid orbit regime classifications "
            "(LEO, MEO, GEO, HEO), verifies that launch date precedes decay date, and flags statistical outliers using Tukey boxplot IQR.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Quarantine & Audit Tracking:</b> Rejected rows are recorded in <code>quality.dead_letter</code> with explicit reason codes "
            "(e.g., <code>INCLINATION_OUT_OF_RANGE</code>, <code>FUTURE_EPOCH</code>). Every validation and pipeline execution generates "
            "immutable audit trail rows in <code>audit.pipeline_runs</code> and <code>audit.data_lineage</code>.",
            bullet_style,
        )
    )
    story.append(Spacer(1, 10))

    # ══════════════════════════════════════════════════════════════════════════
    # 6. DIMENSIONAL STAR SCHEMA (SCHEMA "dw")
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("5. Dimensional Warehouse Architecture (Schema 'dw')", h1_style))
    story.append(
        Paragraph(
            "Rather than relying on 3NF normalized tables that require computationally expensive multi-table joins for analytical queries, "
            "ORBITWATCH models the warehouse as a Kimball-style Dimensional Star Schema residing in schema <code>dw</code>:",
            body_style,
        )
    )

    dw_table_data = [
        [Paragraph("Table Name", th_style), Paragraph("Type", th_style), Paragraph("Grain / Description", th_style), Paragraph("Primary Key", th_style), Paragraph("Row Count", th_style)],
        [Paragraph("dw.dim_date", td_style), Paragraph("Dimension", td_style), Paragraph("1 row per calendar day (1749 to 2030)", td_style), Paragraph("date_key (YYYYMMDD)", td_style), Paragraph("102,998", td_style)],
        [Paragraph("dw.dim_satellite", td_style), Paragraph("Dimension", td_style), Paragraph("1 row per catalogued satellite (SCD Type 1)", td_style), Paragraph("satellite_key (Surrogate)", td_style), Paragraph("70,953", td_style)],
        [Paragraph("dw.dim_orbit_regime", td_style), Paragraph("Dimension", td_style), Paragraph("LEO, MEO, GEO, HEO, UNKNOWN", td_style), Paragraph("regime_id", td_style), Paragraph("5", td_style)],
        [Paragraph("dw.dim_object_type", td_style), Paragraph("Dimension", td_style), Paragraph("Payload, Rocket Body, Debris, Unknown", td_style), Paragraph("object_type_id", td_style), Paragraph("4", td_style)],
        [Paragraph("dw.fact_gp_snapshot", td_style), Paragraph("Fact", td_style), Paragraph("1 row per satellite per epoch snapshot", td_style), Paragraph("snapshot_id", td_style), Paragraph("19,366", td_style)],
        [Paragraph("dw.fact_space_weather_month", td_style), Paragraph("Fact", td_style), Paragraph("1 row per calendar month (F10.7, Sunspot #)", td_style), Paragraph("weather_month_id", td_style), Paragraph("3,333", td_style)],
        [Paragraph("dw.fact_decay_month", td_style), Paragraph("Fact", td_style), Paragraph("1 row per month per regime (Sum = 35,677)", td_style), Paragraph("decay_month_id", td_style), Paragraph("1,535", td_style)],
    ]
    dw_table = Table(dw_table_data, colWidths=[120, 65, 175, 95, 45])
    dw_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COL),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ])
    )
    story.append(dw_table)
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "<b>Atomic Truncate-and-Load ETL:</b> <code>scripts/load_warehouse.py</code> executes within a single PostgreSQL ACID transaction. "
            "If any foreign key validation or aggregation fails, the entire transaction rolls back automatically, preventing partial corruption. "
            "Idempotency was verified across consecutive runs with zero drift in table counts.",
            body_style,
        )
    )
    story.append(Spacer(1, 10))

    # ══════════════════════════════════════════════════════════════════════════
    # 7. LAKEHOUSE & ANALYTICS LAYER (DELTA LAKE + DUCKDB)
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("6. Lakehouse Layer (Delta Lake & DuckDB)", h1_style))
    story.append(
        Paragraph(
            "To offload high-throughput analytical scans from PostgreSQL and support cloud object storage compatibility, "
            "ORBITWATCH implements an ACID Lakehouse layer:",
            body_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Delta Lake Export:</b> <code>scripts/export_lakehouse.py</code> serializes the three fact tables and <code>dim_satellite</code> "
            "into Apache Parquet format under <code>data/lake/</code> wrapped with Delta transaction logs (<code>_delta_log/</code>). "
            "Overwrites maintain transaction history and increment version commits (v0 $\\rightarrow$ v1).",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>DuckDB Vectorized Engine:</b> <code>scripts/query_lake.py</code> initializes DuckDB in-process and registers Delta tables "
            "via PyArrow datasets. DuckDB parses the Delta transaction log, ignores tombstoned parquet files, and executes multi-decade "
            "joins between solar flux and satellite decay counts in under 50 milliseconds.",
            bullet_style,
        )
    )
    story.append(Spacer(1, 10))

    # ══════════════════════════════════════════════════════════════════════════
    # 8. WORKFLOW ORCHESTRATION (PREFECT)
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("7. Workflow Orchestration (Prefect Flow)", h1_style))
    story.append(
        Paragraph(
            "The platform coordinates all operational pipeline steps using <b>Prefect 3.8</b> (<code>flows/orbitwatch_flow.py</code>):",
            body_style,
        )
    )
    story.append(
        Paragraph(
            "1. <code>download_raw_data_task</code>: Downloads fresh ephemerides and solar telemetry with automatic retries "
            "(<code>retries=2</code>, <code>retry_delay=2s</code>).",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "2. <code>run_data_validation_task</code>: Executes Great Expectations quality gates across all staging tables.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "3. <code>load_data_warehouse_task</code>: Executes the atomic dimensional warehouse loader.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "<b>Failure Circuit-Breaker:</b> The tasks are chained sequentially. In fault-injection tests (simulating an unreachable API), "
            "the download task exhausted its retries and transitioned to <code>Failed</code>, which immediately halted downstream validation "
            "and warehouse loading. This guarantees that corrupt upstream data never touches the warehouse.",
            body_style,
        )
    )
    story.append(Spacer(1, 10))

    # ══════════════════════════════════════════════════════════════════════════
    # 9. FRONT-END: STREAMLIT EXECUTIVE DASHBOARD
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("8. Front-End: Operational Intelligence Dashboard", h1_style))
    story.append(
        Paragraph(
            "The front-end user interface is implemented as a single-page, responsive web application in <b>Streamlit</b> "
            "(<code>app/dashboard.py</code>):",
            body_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Role-Based Security:</b> The application connects exclusively using the <code>dashboard_user</code> role. "
            "Permissions are strictly restricted to <code>SELECT</code> on schema <code>dw</code>, verified at runtime via "
            "<code>SELECT current_user</code>. Staging, raw, and audit modifications are blocked at the database level.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Executive KPI Cards:</b> Real-time counters displaying 70,953 catalogued satellites, 19,366 active GP snapshots, "
            "3,333 solar weather observation months, and 35,677 atmospheric re-entry events.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Orbit Regime Population Analysis:</b> Interactive breakdown detailing satellite counts: LEO (62,290; 87.8%), "
            "MEO (3,688; 5.2%), UNKNOWN (2,052; 2.9%), HEO (1,986; 2.8%), and GEO (937; 1.3%).",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Dual-Axis Solar vs. Decay Time Series:</b> Primary axis plots 10.7cm solar radio flux (sfu) and secondary axis plots "
            "monthly satellite re-entries over 70+ years.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Orbital Mechanics Snapshot Table:</b> Aggregates mean motion (rev/day), eccentricity, and inclination across orbital regimes.",
            bullet_style,
        )
    )
    story.append(Spacer(1, 10))

    # ══════════════════════════════════════════════════════════════════════════
    # 10. SCIENTIFIC & STATISTICAL FINDINGS
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("9. Scientific Analysis: Solar Flux vs. Orbital Decay", h1_style))
    story.append(
        Paragraph(
            "A core research question of ORBITWATCH is quantifying the relationship between solar electromagnetic output and "
            "satellite re-entry rates:",
            body_style,
        )
    )
    story.append(
        Paragraph(
            "<b>Statistical Findings:</b> Pearson correlation analysis across <b>808 monthly observations</b> reveals a correlation "
            "coefficient of <b>r = 0.7060</b>, indicating a <i>strong, statistically significant positive correlation</i> between "
            "solar radio flux (F10.7) and atmospheric decay events.",
            body_style,
        )
    )

    callout_data = [[
        Paragraph(
            "<b>Scientific Caveat (Correlation vs. Causation):</b> While solar EUV heating physically expands the thermosphere "
            "and increases aerodynamic drag, observed monthly decay totals are also modulated by human launch volume, mega-constellation "
            "end-of-life deorbiting policies, and historical space tracking coverage. Solar flux is the primary physical driver, but not the sole factor.",
            callout_style,
        )
    ]]
    callout_table = Table(callout_data, colWidths=[500])
    callout_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF3C7")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#D97706")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ])
    )
    story.append(callout_table)
    story.append(Spacer(1, 14))

    # ══════════════════════════════════════════════════════════════════════════
    # 11. TESTING, VERIFICATION & VIVA HIGHLIGHTS
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("10. Verification, Testing & Oral Defense Guide", h1_style))
    story.append(
        Paragraph(
            "The platform was verified through a comprehensive 43-test automated test suite (<code>pytest -v</code>) with 100% pass rate:",
            body_style,
        )
    )

    test_table_data = [
        [Paragraph("Test Suite", th_style), Paragraph("Scope / Functionality Verified", th_style), Paragraph("Tests", th_style), Paragraph("Outcome", th_style)],
        [Paragraph("test_cleaning.py", td_style), Paragraph("Domain cleaning, outlier detection, string stripping", td_style), Paragraph("4", td_style), Paragraph("PASSED", td_style)],
        [Paragraph("test_healthcheck.py", td_style), Paragraph("PostgreSQL, MongoDB, and Redpanda connectivity", td_style), Paragraph("3", td_style), Paragraph("PASSED", td_style)],
        [Paragraph("test_ingestion_api.py", td_style), Paragraph("FastAPI auth, duplicate keys, payload validation", td_style), Paragraph("5", td_style), Paragraph("PASSED", td_style)],
        [Paragraph("test_streaming.py", td_style), Paragraph("Deterministic UUID5 events, envelope parsing", td_style), Paragraph("3", td_style), Paragraph("PASSED", td_style)],
        [Paragraph("test_validation.py", td_style), Paragraph("Great Expectations Raw and Clean expectation suites", td_style), Paragraph("22", td_style), Paragraph("PASSED", td_style)],
        [Paragraph("test_warehouse.py", td_style), Paragraph("Date keys, stage reconciliation, zero orphan FKs, RBAC", td_style), Paragraph("6", td_style), Paragraph("PASSED", td_style)],
    ]
    test_table = Table(test_table_data, colWidths=[110, 240, 50, 100])
    test_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), SECONDARY),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COL),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ])
    )
    story.append(test_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Key Oral Defense (Viva) Questions & Answers:", h2_style))
    story.append(
        Paragraph(
            "<b>Q1: Why choose a Kimball Star Schema over a 3NF Core model?</b><br/>"
            "<i>A: Space domain analytics requires multi-dimensional slicing across time, regime, and solar flux. "
            "Star schemas denormalize dimension attributes, drastically reducing join overhead and producing predictable query plans for reporting tools.</i>",
            body_style,
        )
    )
    story.append(
        Paragraph(
            "<b>Q2: How does Delta Lake prevent reading partial data during concurrent exports?</b><br/>"
            "<i>A: Delta Lake enforces ACID transactions via its JSON commit log (<code>_delta_log</code>). Readers only query files "
            "referenced in committed transaction versions; uncommitted or tombstoned parquet files are filtered out automatically.</i>",
            body_style,
        )
    )
    story.append(
        Paragraph(
            "<b>Q3: What are the main limitations of the platform?</b><br/>"
            "<i>A: (1) Future epoch rule: GP data must satisfy <code>EPOCH &le; now(UTC)</code>, meaning forward-propagated ephemerides are quarantined. "
            "(2) K-index horizon: The SWPC 1-minute feed is limited to a rolling 24-hour window (359 rows), so it was excluded from multi-decade warehouse facts.</i>",
            body_style,
        )
    )

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[OK] Generated Deep Analysis PDF: {OUTPUT_PDF}")
    return OUTPUT_PDF


if __name__ == "__main__":
    create_deep_analysis_pdf()
