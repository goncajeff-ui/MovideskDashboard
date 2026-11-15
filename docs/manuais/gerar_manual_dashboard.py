#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Manual Executivo de Leitura — Dashboard Movidesk BI (Sala de Guerra)
====================================================================
Gera o PDF oficial e HTML autocontido do "Manual Executivo de Leitura da
Sala de Guerra - Movidesk BI" no padrão visual corporativo da Advice
Compliance Solutions (Azul-Petróleo #0B3B52 e Dourado #C59217).

Motor principal de PDF:
  - WeasyPrint (recomendado: HTML/CSS -> PDF vetorial de alta fidelidade)
Fallback automático (caso WeasyPrint/GTK não esteja instalado no host):
  - Google Chrome / Microsoft Edge / Chromium em modo --headless --print-to-pdf

Como executar:
  python docs/manuais/gerar_manual_dashboard.py
"""

from __future__ import annotations

import argparse
import base64
import html
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple


BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"

MANUAL_TITLE_HEADER = "MANUAL EXECUTIVO — DASHBOARD MOVIDESK BI (SALA DE GUERRA)"
OUTPUT_BASENAME = "Manual_04_Leitura_Executiva_Dashboard_Movidesk_BI"

ODT_SCREENSHOT_ORDER: List[str] = [
    "dash_01_kpi_backlog.png",
    "dash_02_kpi_sla_vencidos.png",
    "dash_03_kpi_sla_iminente.png",
    "dash_04_kpi_abertos_hoje.png",
    "dash_05_kpi_resolvidos_hoje.png",
    "dash_06_kpi_fcr_30d.png",
    "dash_07_radar_preditivo_sla.png",
    "dash_08_evolucao_backlog_90d.png",
    "dash_09_throughput_diario.png",
    "dash_10_auditoria_envelhecimento.png",
    "dash_11_gargalos_status.png",
    "dash_12_mapa_demanda.png",
    "dash_13_raio_x_clientes.png",
    "dash_14_donut_clientes.png",
    "dash_15_grid_clientes_periodo.png",
]


def ensure_assets(odt_fallback: Optional[Path] = None) -> None:
    """Garante que os 15 prints reais do Dashboard estejam disponíveis em assets/."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    missing = [name for name in ODT_SCREENSHOT_ORDER if not (ASSETS_DIR / name).exists()]
    if not missing:
        return

    candidates: List[Path] = []
    if odt_fallback:
        candidates.append(odt_fallback)
    candidates.extend(
        [
            BASE_DIR / "Prints_Dashboard.odt",
            BASE_DIR.parent.parent / "Prints_Dashboard.odt",
            Path.home() / "Prints_Dashboard.odt",
        ]
    )

    odt_path = next((p for p in candidates if p.exists()), None)
    if not odt_path:
        print(
            f"[AVISO] Screenshots ausentes em {ASSETS_DIR}: {', '.join(missing)}",
            file=sys.stderr,
        )
        return

    try:
        with zipfile.ZipFile(odt_path, "r") as zf:
            xml_bytes = zf.read("content.xml")
            root = ET.fromstring(xml_bytes)
            ns = {"draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"}
            ns_xlink = "{http://www.w3.org/1999/xlink}href"
            ordered_hrefs: List[str] = []
            for img_el in root.findall(".//draw:image", ns):
                href = img_el.attrib.get(ns_xlink, "")
                if href and href not in ordered_hrefs:
                    ordered_hrefs.append(href)
            for idx, target_name in enumerate(ODT_SCREENSHOT_ORDER):
                target_path = ASSETS_DIR / target_name
                if target_path.exists() or idx >= len(ordered_hrefs):
                    continue
                target_path.write_bytes(zf.read(ordered_hrefs[idx]))
        print(f"[OK] Screenshots extraídos de {odt_path.name} para {ASSETS_DIR}.")
    except Exception as exc:
        print(f"[AVISO] Falha ao extrair screenshots de {odt_path}: {exc}", file=sys.stderr)


def img_data_uri(filename: str) -> str:
    """Converte uma captura PNG de assets/ em Data URI base64."""
    path = ASSETS_DIR / filename
    if not path.exists():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


CSS_STYLES = """
@page {
    size: A4 portrait;
    margin: 0;
}

* {
    box-sizing: border-box;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}

html, body {
    margin: 0;
    padding: 0;
    background-color: #cbd5e1;
    font-family: 'Open Sans', 'Segoe UI', 'Liberation Sans', 'DejaVu Sans', Arial, sans-serif;
    color: #1e293b;
    font-size: 8.6pt;
    line-height: 1.38;
}

@media print {
    html, body {
        background-color: #ffffff;
    }
    .pdf-page {
        margin: 0 !important;
        box-shadow: none !important;
    }
}

.pdf-page {
    width: 210mm;
    height: 296.8mm;
    background-color: #ffffff;
    margin: 6mm auto;
    box-shadow: 0 6px 24px rgba(15, 23, 42, 0.16);
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    position: relative;
    overflow: hidden;
    page-break-after: always;
    break-after: page;
}

.pdf-page:last-child {
    page-break-after: auto;
    break-after: auto;
}

/* =========================================================================
   CABEÇALHO E RODAPÉ PADRÃO ADVICE COMPLIANCE SOLUTIONS
   ========================================================================= */
.page-header {
    background: linear-gradient(90deg, #093246 0%, #0F435C 100%);
    color: #ffffff;
    padding: 3.6mm 12mm;
    border-bottom: 1.1mm solid #C59217;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
}

.brand-left {
    font-size: 8.2pt;
    font-weight: 800;
    letter-spacing: 0.7px;
    text-transform: uppercase;
    color: #ffffff;
    display: flex;
    align-items: center;
    gap: 2mm;
    white-space: nowrap;
}

.brand-dot {
    width: 2.2mm;
    height: 2.2mm;
    background-color: #C59217;
    border-radius: 50%;
    display: inline-block;
    flex-shrink: 0;
}

.manual-title-right {
    font-size: 7.2pt;
    font-weight: 700;
    color: #f1f5f9;
    letter-spacing: 0.2px;
    text-align: right;
    white-space: nowrap;
}

.page-body {
    flex: 1;
    padding: 4.8mm 12mm 3.8mm 12mm;
    display: flex;
    flex-direction: column;
    gap: 2.8mm;
    overflow: hidden;
}

.page-footer {
    padding: 2.6mm 12mm 3.6mm 12mm;
    border-top: 0.45mm solid #cbd5e1;
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 7.6pt;
    color: #475569;
    background-color: #ffffff;
    flex-shrink: 0;
}

.footer-left {
    font-weight: 700;
    color: #0B3B52;
}

.footer-right {
    font-weight: 800;
    color: #B3820E;
}

/* =========================================================================
   CAPA, DESTAQUES E SUMÁRIO
   ========================================================================= */
.cover-banner {
    background: linear-gradient(135deg, #0B3B52 0%, #124E6B 100%);
    color: #ffffff;
    border-radius: 2mm;
    padding: 5.5mm 6.5mm;
    border-left: 2.2mm solid #C59217;
}

.cover-tag {
    display: inline-block;
    background-color: #C59217;
    color: #ffffff;
    font-size: 7.1pt;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    padding: 0.9mm 2.5mm;
    border-radius: 1mm;
    margin-bottom: 1.8mm;
}

.cover-banner h1 {
    margin: 0 0 1.6mm 0;
    font-size: 16.5pt;
    font-weight: 800;
    line-height: 1.16;
    color: #ffffff;
}

.cover-banner p {
    margin: 0;
    font-size: 8.6pt;
    color: #e2e8f0;
    line-height: 1.38;
}

.cover-meta-strip {
    margin-top: 3mm;
    padding-top: 2.2mm;
    border-top: 1px solid rgba(255, 255, 255, 0.22);
    font-size: 7.5pt;
    color: #f8fafc;
}

.cover-meta-table {
    width: 100%;
    border-collapse: collapse;
}

.cover-meta-table td {
    color: #f8fafc;
    font-size: 7.4pt;
    padding: 0;
}

.cover-meta-table strong {
    color: #F3C65F;
}

.cover-meta-table code {
    background-color: rgba(255, 255, 255, 0.16);
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.24);
    font-size: 7pt;
    padding: 0.15mm 1.1mm;
}

.section-heading-gold {
    display: flex;
    align-items: center;
    gap: 2.5mm;
    margin: 0.5mm 0 0 0;
}

.section-heading-gold h2 {
    margin: 0;
    font-size: 9.8pt;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #0B3B52;
    white-space: nowrap;
}

.gold-line {
    flex: 1;
    height: 0.55mm;
    background: linear-gradient(90deg, #C59217 0%, #e2e8f0 100%);
}

/* Tabela de 2x2 Destaques (compatível com todas versões WeasyPrint) */
.highlights-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 2.6mm;
    margin: -2.6mm;
}

.highlights-cell {
    width: 50%;
    vertical-align: top;
    background-color: #f8fafc;
    border: 1px solid #cbd5e1;
    border-top: 1mm solid #0B3B52;
    border-radius: 1.5mm;
    padding: 2.8mm 3.2mm;
}

.hl-layout {
    width: 100%;
    border-collapse: collapse;
}

.hl-num-td {
    width: 9mm;
    vertical-align: top;
}

.highlight-num {
    background-color: #C59217;
    color: #ffffff;
    font-size: 10pt;
    font-weight: 800;
    width: 7.5mm;
    height: 7.5mm;
    line-height: 7.5mm;
    text-align: center;
    border-radius: 1.2mm;
}

.hl-content-td h3 {
    margin: 0 0 0.8mm 0;
    font-size: 8.8pt;
    font-weight: 800;
    color: #0B3B52;
}

.hl-content-td p {
    margin: 0;
    font-size: 7.8pt;
    color: #334155;
    line-height: 1.32;
}

/* Caixa de Filtros Globais na Capa */
.filters-guide-box {
    background-color: #fffbeb;
    border: 1px solid #fcd34d;
    border-left: 1.6mm solid #C59217;
    border-radius: 1.4mm;
    padding: 2.6mm 3.4mm;
}

.filters-guide-title {
    font-size: 8.5pt;
    font-weight: 800;
    color: #0B3B52;
    margin-bottom: 1.2mm;
}

.filters-mini-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 7.6pt;
}

.filters-mini-table td {
    padding: 0.7mm 1.4mm;
    vertical-align: top;
    border-bottom: 1px dashed #fde68a;
    color: #334155;
}

.filters-mini-table tr:last-child td {
    border-bottom: none;
}

/* Sumário / Índice */
.toc-box {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-left: 1.6mm solid #0B3B52;
    border-radius: 1.5mm;
    padding: 2.8mm 3.8mm;
}

.toc-table {
    width: 100%;
    border-collapse: collapse;
}

.toc-table td {
    padding: 1.05mm 0;
    border-bottom: 1px dashed #cbd5e1;
    font-size: 8pt;
    vertical-align: middle;
}

.toc-table tr:last-child td {
    border-bottom: none;
}

.toc-badge {
    display: inline-block;
    background-color: #0B3B52;
    color: #ffffff;
    font-weight: 800;
    font-size: 6.9pt;
    padding: 0.45mm 1.8mm;
    border-radius: 0.8mm;
    margin-right: 1.6mm;
}

.toc-title {
    font-weight: 700;
    color: #0B3B52;
}

.toc-desc {
    color: #64748b;
    font-size: 7.5pt;
}

.toc-page {
    text-align: right;
    font-weight: 800;
    color: #B3820E;
    font-size: 7.9pt;
    white-space: nowrap;
}

/* =========================================================================
   CABEÇALHO DE CAPÍTULO / BLOCO
   ========================================================================= */
.chapter-header {
    display: flex;
    align-items: center;
    gap: 3mm;
    border-bottom: 0.7mm solid #0B3B52;
    padding-bottom: 1.8mm;
}

.chapter-badge {
    background-color: #C59217;
    color: #ffffff;
    font-size: 8.2pt;
    font-weight: 800;
    padding: 1.2mm 2.8mm;
    border-radius: 1.2mm;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    white-space: nowrap;
    flex-shrink: 0;
}

.chapter-title-block h2 {
    margin: 0;
    font-size: 11.6pt;
    font-weight: 800;
    color: #0B3B52;
    line-height: 1.15;
}

.chapter-title-block span {
    font-size: 7.7pt;
    color: #B3820E;
    font-weight: 700;
}

/* =========================================================================
   CARDS DE COMPONENTES (KPIs & VISUALIZAÇÕES COMPLETAS)
   ========================================================================= */
.comp-card {
    border: 1px solid #cbd5e1;
    border-top: 0.8mm solid #0B3B52;
    border-radius: 1.5mm;
    background-color: #ffffff;
    overflow: hidden;
}

.comp-card-head {
    background-color: #f1f5f9;
    padding: 1.35mm 2.5mm;
    border-bottom: 1px solid #cbd5e1;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 2mm;
}

.comp-head-left {
    display: flex;
    align-items: center;
    gap: 1.8mm;
}

.comp-num {
    background-color: #0B3B52;
    color: #ffffff;
    font-size: 7.2pt;
    font-weight: 800;
    padding: 0.4mm 1.6mm;
    border-radius: 0.9mm;
    flex-shrink: 0;
}

.comp-title {
    font-size: 8.5pt;
    font-weight: 800;
    color: #0B3B52;
    white-space: nowrap;
}

.comp-meta-pill {
    font-family: 'Consolas', 'DejaVu Sans Mono', monospace;
    font-size: 6.6pt;
    font-weight: 700;
    color: #0B3B52;
    background-color: #e2e8f0;
    padding: 0.35mm 1.5mm;
    border-radius: 0.8mm;
    border: 1px solid #cbd5e1;
    white-space: nowrap;
    flex-shrink: 0;
}

.comp-card-body {
    padding: 1.8mm 2.4mm;
    display: flex;
    flex-direction: column;
    gap: 1.5mm;
}

/* KPI Layout (Imagem à esquerda + Resumo à direita + 2 faixas abaixo) */
.kpi-top-table {
    width: 100%;
    border-collapse: collapse;
}

.kpi-img-cell {
    width: 59mm;
    vertical-align: middle;
    padding-right: 2.8mm;
}

.kpi-img-frame {
    background-color: #0b0e14;
    border: 1px solid #0B3B52;
    border-radius: 1.2mm;
    padding: 1mm;
    text-align: center;
}

.kpi-img-frame img {
    width: 100%;
    height: auto;
    display: block;
    border-radius: 0.6mm;
}

.kpi-def-cell {
    vertical-align: middle;
}

/* Wide Screenshot Frame */
.wide-img-frame {
    background-color: #0b0e14;
    border: 1px solid #0B3B52;
    border-radius: 1.2mm;
    padding: 1mm;
    text-align: center;
}

.wide-img-frame img {
    display: block;
    margin: 0 auto;
    max-width: 100%;
    width: auto;
    height: auto;
    border-radius: 0.5mm;
}

.wide-img-caption {
    margin-top: 0.7mm;
    font-size: 6.8pt;
    color: #cbd5e1;
    font-weight: 600;
    letter-spacing: 0.2px;
}

/* Caixas Didáticas: O que é / Como ler / Ação Sugerida */
.guide-block-oquee {
    background-color: #f8fafc;
    border-left: 1.1mm solid #0B3B52;
    padding: 1.2mm 2.3mm;
    border-radius: 0.8mm;
    font-size: 8pt;
    color: #1e293b;
}

.guide-block-comoler {
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-left: 1.1mm solid #0284c7;
    padding: 1.3mm 2.3mm;
    border-radius: 0.8mm;
    font-size: 7.9pt;
    color: #1e293b;
}

.guide-block-acao {
    background-color: #fffbeb;
    border: 1px solid #fde68a;
    border-left: 1.1mm solid #C59217;
    padding: 1.3mm 2.3mm;
    border-radius: 0.8mm;
    font-size: 7.9pt;
    color: #451a03;
}

.lbl-oquee {
    font-weight: 800;
    color: #0B3B52;
    text-transform: uppercase;
    font-size: 7.3pt;
    letter-spacing: 0.3px;
}

.lbl-comoler {
    font-weight: 800;
    color: #0369a1;
    text-transform: uppercase;
    font-size: 7.3pt;
    letter-spacing: 0.3px;
}

.lbl-acao {
    font-weight: 800;
    color: #92400e;
    text-transform: uppercase;
    font-size: 7.3pt;
    letter-spacing: 0.3px;
}

.dual-guide-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 2mm 0;
    margin: 0 -2mm;
}

.dual-guide-table td {
    width: 50%;
    vertical-align: top;
}

/* =========================================================================
   TABELAS ZEBRADAS CORPORATIVAS E CALLOUTS
   ========================================================================= */
.zebra-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 7.5pt;
    border: 1px solid #cbd5e1;
}

.zebra-table thead tr {
    background-color: #0B3B52;
    color: #ffffff;
}

.zebra-table thead th {
    padding: 1.3mm 2.1mm;
    text-align: left;
    font-weight: 800;
    letter-spacing: 0.2px;
    border-bottom: 0.7mm solid #C59217;
    font-size: 7.3pt;
}

.zebra-table tbody td {
    padding: 1.1mm 2.1mm;
    border-bottom: 1px solid #e2e8f0;
    color: #1e293b;
    vertical-align: top;
    line-height: 1.26;
}

.zebra-table.compact {
    font-size: 7.15pt;
}

.zebra-table.compact thead th {
    padding: 1mm 1.8mm;
    font-size: 7pt;
}

.zebra-table.compact tbody td {
    padding: 0.8mm 1.8mm;
    line-height: 1.22;
}

.zebra-table tbody tr:nth-child(even) {
    background-color: #f1f5f9;
}

.zebra-table tbody tr:nth-child(odd) {
    background-color: #ffffff;
}

.callout-navy {
    background-color: #f0f9ff;
    border: 1px solid #bae6fd;
    border-left: 1.5mm solid #0B3B52;
    border-radius: 1.2mm;
    padding: 2mm 2.8mm;
    font-size: 7.9pt;
    color: #0f172a;
}

.callout-gold {
    background-color: #fffbeb;
    border: 1px solid #fcd34d;
    border-left: 1.5mm solid #C59217;
    border-radius: 1.2mm;
    padding: 2mm 2.8mm;
    font-size: 7.9pt;
    color: #78350f;
}

code {
    font-family: 'Consolas', 'DejaVu Sans Mono', monospace;
    font-size: 7.3pt;
    background-color: #e2e8f0;
    color: #0B3B52;
    padding: 0.15mm 1mm;
    border-radius: 0.6mm;
    font-weight: 700;
}

.pill-red {
    display: inline-block;
    background-color: #fee2e2;
    color: #991b1b;
    border: 1px solid #fca5a5;
    padding: 0.25mm 1.4mm;
    border-radius: 0.7mm;
    font-weight: 800;
    font-size: 6.9pt;
}

.pill-amber {
    display: inline-block;
    background-color: #fef3c7;
    color: #92400e;
    border: 1px solid #fcd34d;
    padding: 0.25mm 1.4mm;
    border-radius: 0.7mm;
    font-weight: 800;
    font-size: 6.9pt;
}

.pill-green {
    display: inline-block;
    background-color: #d1fae5;
    color: #065f46;
    border: 1px solid #6ee7b7;
    padding: 0.25mm 1.4mm;
    border-radius: 0.7mm;
    font-weight: 800;
    font-size: 6.9pt;
}

.pill-slate {
    display: inline-block;
    background-color: #e2e8f0;
    color: #334155;
    border: 1px solid #cbd5e1;
    padding: 0.25mm 1.4mm;
    border-radius: 0.7mm;
    font-weight: 800;
    font-size: 6.9pt;
}
"""


def render_page(body_html: str, page_num: int, total_pages: int) -> str:
    """Envolve o conteúdo no template oficial A4 (Cabeçalho + Corpo + Rodapé)."""
    return f"""
    <section class="pdf-page">
        <header class="page-header">
            <div class="brand-left">
                <span class="brand-dot"></span>
                <span>ADVICE COMPLIANCE SOLUTIONS</span>
            </div>
            <div class="manual-title-right">{html.escape(MANUAL_TITLE_HEADER)}</div>
        </header>
        <main class="page-body">
            {body_html}
        </main>
        <footer class="page-footer">
            <div class="footer-left">Advice Compliance Solutions &mdash; Movidesk BI &amp; Governança Operacional</div>
            <div class="footer-right">Página {page_num} de {total_pages}</div>
        </footer>
    </section>
    """


def render_kpi_card(
    num: str,
    title: str,
    img_filename: str,
    dataset_pill: str,
    regra_curta: str,
    o_que_e: str,
    como_ler: str,
    acao_sugerida: str,
) -> str:
    """Renderiza um card didático para os Big Numbers do Bloco 1."""
    uri = img_data_uri(img_filename)
    img_tag = (
        f'<img src="{uri}" alt="{html.escape(title)}" />'
        if uri
        else f'<div style="color:#94a3b8;font-size:7pt;padding:4mm;">{html.escape(img_filename)}</div>'
    )
    return f"""
    <div class="comp-card">
        <div class="comp-card-head">
            <div class="comp-head-left">
                <span class="comp-num">{html.escape(num)}</span>
                <span class="comp-title">{html.escape(title)}</span>
            </div>
            <span class="comp-meta-pill">{html.escape(dataset_pill)}</span>
        </div>
        <div class="comp-card-body">
            <table class="kpi-top-table">
                <tr>
                    <td class="kpi-img-cell">
                        <div class="kpi-img-frame">{img_tag}</div>
                    </td>
                    <td class="kpi-def-cell">
                        <div class="guide-block-oquee">
                            <span class="lbl-oquee">O que é:</span> {o_que_e}<br/>
                            <span style="font-size:7.3pt;color:#475569;"><strong>Regra técnica:</strong> {regra_curta}</span>
                        </div>
                    </td>
                </tr>
            </table>
            <table class="dual-guide-table">
                <tr>
                    <td>
                        <div class="guide-block-comoler">
                            <span class="lbl-comoler">Como ler:</span> {como_ler}
                        </div>
                    </td>
                    <td>
                        <div class="guide-block-acao">
                            <span class="lbl-acao">Ação Sugerida:</span> {acao_sugerida}
                        </div>
                    </td>
                </tr>
            </table>
        </div>
    </div>
    """


def render_wide_component(
    num: str,
    title: str,
    img_filename: str,
    caption: str,
    dataset_pill: str,
    o_que_e: str,
    como_ler: str,
    acao_sugerida: str,
    img_max_height: str = "39mm",
    extra_html: str = "",
) -> str:
    """Renderiza um card completo com print em largura total, O que é, Como ler e Ação Sugerida."""
    uri = img_data_uri(img_filename)
    img_tag = (
        f'<img src="{uri}" style="max-height:{img_max_height};" alt="{html.escape(title)}" />'
        if uri
        else f'<div style="color:#94a3b8;font-size:7.5pt;padding:6mm;">Imagem ausente: {html.escape(img_filename)}</div>'
    )
    return f"""
    <div class="comp-card">
        <div class="comp-card-head">
            <div class="comp-head-left">
                <span class="comp-num">{html.escape(num)}</span>
                <span class="comp-title">{html.escape(title)}</span>
            </div>
            <span class="comp-meta-pill">{html.escape(dataset_pill)}</span>
        </div>
        <div class="comp-card-body">
            <div class="wide-img-frame">
                {img_tag}
                <div class="wide-img-caption">{html.escape(caption)}</div>
            </div>
            <div class="guide-block-oquee">
                <span class="lbl-oquee">O que é:</span> {o_que_e}
            </div>
            <table class="dual-guide-table">
                <tr>
                    <td>
                        <div class="guide-block-comoler">
                            <span class="lbl-comoler">Como ler:</span> {como_ler}
                        </div>
                    </td>
                    <td>
                        <div class="guide-block-acao">
                            <span class="lbl-acao">Ação Sugerida:</span> {acao_sugerida}
                        </div>
                    </td>
                </tr>
            </table>
            {extra_html}
        </div>
    </div>
    """


def build_pages() -> List[str]:
    """Constrói todas as 8 páginas do Manual Executivo de Leitura."""
    pages: List[str] = []

    # =========================================================================
    # PÁGINA 1: CAPA EXECUTIVA, FILTROS GLOBAIS E ÍNDICE
    # =========================================================================
    p1 = """
    <div class="cover-banner">
        <div class="cover-tag">Guia Oficial de Decisão Gerencial &bull; Movidesk BI</div>
        <h1>Manual Executivo de Leitura da Sala de Guerra<br/>&mdash; Dashboard Movidesk BI</h1>
        <p>
            Guia prático para Gestores, Coordenadores de Sustentação e Customer Success da
            <strong>Advice Compliance Solutions</strong> interpretarem os <strong>15 componentes</strong> do painel
            analítico (publicado no Apache Superset como <strong>Dashboard - Movidesk BI</strong>, antiga <em>Sala de Guerra</em>),
            transformando métricas em ações rápidas de SLA, produtividade e retenção de clientes.
        </p>
        <div class="cover-meta-strip">
            <table class="cover-meta-table">
                <tr>
                    <td><strong>Plataforma:</strong> Apache Superset 6.1.0</td>
                    <td><strong>Data Mart:</strong> SQL Server <code>MovideskDM</code> (<code>mart.vw_*</code>)</td>
                    <td><strong>Fuso:</strong> Horário de Brasília (BRT)</td>
                    <td><strong>Refresh Auto:</strong> A cada 60 segundos</td>
                </tr>
            </table>
        </div>
    </div>

    <div class="section-heading-gold">
        <h2>Os 4 Blocos de Inteligência do Painel</h2>
        <div class="gold-line"></div>
    </div>

    <table class="highlights-table">
        <tr>
            <td class="highlights-cell">
                <table class="hl-layout">
                    <tr>
                        <td class="hl-num-td"><div class="highlight-num">01</div></td>
                        <td class="hl-content-td">
                            <h3>Bloco 1: Big Numbers (Saúde Imediata)</h3>
                            <p>Seis termômetros de topo para leitura em 10 segundos: Backlog Atual, SLA Vencidos, SLA Iminente (&lt; 4h), Abertos Hoje, Resolvidos Hoje e FCR 30 Dias (%).</p>
                        </td>
                    </tr>
                </table>
            </td>
            <td class="highlights-cell">
                <table class="hl-layout">
                    <tr>
                        <td class="hl-num-td"><div class="highlight-num">02</div></td>
                        <td class="hl-content-td">
                            <h3>Bloco 2: Monitoramento de Fila e Vazão</h3>
                            <p>Priorização cirúrgica da fila ativa (Radar Preditivo por gravidade e minutos para vencer), tendência de 90 dias (&ldquo;montanhas&rdquo;) e equilíbrio Abertos vs Resolvidos.</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
        <tr>
            <td class="highlights-cell">
                <table class="hl-layout">
                    <tr>
                        <td class="hl-num-td"><div class="highlight-num">03</div></td>
                        <td class="hl-content-td">
                            <h3>Bloco 3: Auditoria e Gargalos (Eficiência)</h3>
                            <p>Caça a tickets esquecidos (+48h sem ação), comparação entre Horas Úteis e Horas Corridas por status e mapa de demanda por Serviço, Categoria e Versão.</p>
                        </td>
                    </tr>
                </table>
            </td>
            <td class="highlights-cell">
                <table class="hl-layout">
                    <tr>
                        <td class="hl-num-td"><div class="highlight-num">04</div></td>
                        <td class="hl-content-td">
                            <h3>Bloco 4: Sucesso do Cliente (CS &amp; Churn)</h3>
                            <p>Radar de Churn para contas silenciosas (&gt; 60 dias por produto/serviço e Dono Atual), somado ao Donut e ao Grid de concentração de chamados no período.</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>

    <div class="filters-guide-box">
        <div class="filters-guide-title">Regra de Ouro antes de Ler Qualquer Número: Como Operar os 3 Filtros Globais</div>
        <table class="filters-mini-table">
            <tr>
                <td style="width:28%;"><strong>1. Filtro <code>Equipe</code></strong></td>
                <td>Atua em <strong>todos os 15 componentes</strong>. Cada coordenação deve selecionar sua equipe (ex.: <em>Sustentação e-Guardian RJ</em>, <em>Sustentação Aquilla RJ</em>) para isolar seu escopo operacional.</td>
            </tr>
            <tr>
                <td><strong>2. Filtro <code>Serviço</code></strong></td>
                <td>Atua nos <strong>6 painéis de produto</strong> (Radar SLA, Aging, Mapa de Demanda, Raio-X de Churn, Donut e Grid de Clientes). Evita misturar chamados de <em>EGUARDIAN</em>, <em>AQUILLA</em>, <em>CCS</em> ou <em>KN1</em> no mesmo banco.</td>
            </tr>
            <tr>
                <td><strong>3. Filtro <code>Período</code></strong></td>
                <td>Controla a coluna <code>DataAbertura</code> no <strong>Donut (14)</strong> e no <strong>Grid de Clientes (15)</strong> &mdash; padrão inicial: <em>Este mês</em>. O ícone azul <span style="background:#0284c7;color:#fff;padding:0.2mm 1.2mm;border-radius:50%;font-weight:800;font-size:6.8pt;">1</span> no canto do card confirma quantos filtros estão ativos.</td>
            </tr>
        </table>
    </div>

    <div class="section-heading-gold">
        <h2>Índice Completo dos 15 Componentes</h2>
        <div class="gold-line"></div>
    </div>

    <div class="toc-box">
        <table class="toc-table">
            <tr>
                <td><span class="toc-badge">BLOCO 1</span><span class="toc-title">KPIs 1 a 3 &mdash; Pressão Imediata: Backlog Atual, SLA Vencidos e SLA Iminente (&lt; 4h)</span><br/><span class="toc-desc">Visão instantânea do tamanho da fila viva e dos prazos críticos em risco.</span></td>
                <td class="toc-page">Página 2</td>
            </tr>
            <tr>
                <td><span class="toc-badge">BLOCO 1</span><span class="toc-title">KPIs 4 a 6 &mdash; Ritmo do Dia: Abertos Hoje, Resolvidos Hoje e FCR 30 Dias (%)</span><br/><span class="toc-desc">Balanço diário de entrada/saída, resolutividade no 1º contato e tabela semáforo matinal.</span></td>
                <td class="toc-page">Página 3</td>
            </tr>
            <tr>
                <td><span class="toc-badge">BLOCO 2</span><span class="toc-title">Componentes 7 e 8 &mdash; Radar Preditivo de SLA (Fila Viva) e Evolução (90 Dias)</span><br/><span class="toc-desc">Tabela de priorização (OrdemGravidade 1 a 7) e gráfico de área em &ldquo;montanhas&rdquo;.</span></td>
                <td class="toc-page">Página 4</td>
            </tr>
            <tr>
                <td><span class="toc-badge">BLOCOS 2-3</span><span class="toc-title">Componentes 9 e 10 &mdash; Throughput Diário e Auditoria de Envelhecimento (+48h Sem Ação)</span><br/><span class="toc-desc">Sinalização de &ldquo;queima de fila&rdquo; vs acúmulo e caça a chamados parados na fila.</span></td>
                <td class="toc-page">Página 5</td>
            </tr>
            <tr>
                <td><span class="toc-badge">BLOCO 3</span><span class="toc-title">Componentes 11 e 12 &mdash; Gargalos por Status e Mapa de Demanda (Serviço / Versão)</span><br/><span class="toc-desc">Diferença prática entre Horas Úteis e Horas Corridas + onde o tempo é drenado.</span></td>
                <td class="toc-page">Página 6</td>
            </tr>
            <tr>
                <td><span class="toc-badge">BLOCO 4</span><span class="toc-title">Componente 13 &mdash; Raio-X de Empresas Clientes e Radar de Churn (Silenciosos &gt; 60d)</span><br/><span class="toc-desc">Critério de silêncio por produto/serviço, Dono Atual (último ticket) e plano CS.</span></td>
                <td class="toc-page">Página 7</td>
            </tr>
            <tr>
                <td><span class="toc-badge">BLOCO 4</span><span class="toc-title">Componentes 14 e 15 &mdash; Donut &amp; Grid: Detalhamento de Tickets por Cliente no Período</span><br/><span class="toc-desc">Concentração de demanda por organização/produto e cadência de rituais de gestão.</span></td>
                <td class="toc-page">Página 8</td>
            </tr>
        </table>
    </div>
    """
    pages.append(p1)

    # =========================================================================
    # PÁGINA 2: BLOCO 1 (PARTE 1) — KPIs 1, 2 e 3
    # =========================================================================
    kpi_1 = render_kpi_card(
        num="01",
        title="KPI - Backlog Atual",
        img_filename="dash_01_kpi_backlog.png",
        dataset_pill="vw_VisaoGeralKpis · SUM(BacklogAtual)",
        regra_curta="Tickets com StatusBase diferente de Resolved, Closed e Canceled (e EhFinal = 0 em Dim_Status).",
        o_que_e="Total exato de chamados ativos e ainda não encerrados na fila da operação neste momento.",
        como_ler="Representa o &ldquo;estoque de trabalho vivo&rdquo; sob responsabilidade da equipe filtrada (no exemplo, 129 chamados). Compare sempre o valor atual com a capacidade diária da equipe e acompanhe se ele está subindo ou caindo no gráfico de 90 dias (item 8).",
        acao_sugerida="Se o Backlog crescer por 3 dias seguidos acima do teto da equipe, suspenda demandas não urgentes, faça força-tarefa de triagem para fechar &ldquo;Aguardando Cliente&rdquo; expirados e redistribua chamados de analistas sobrecarregados.",
    )
    kpi_2 = render_kpi_card(
        num="02",
        title="KPI - SLA Vencidos",
        img_filename="dash_02_kpi_sla_vencidos.png",
        dataset_pill="vw_VisaoGeralKpis · SUM(SlaVencidos)",
        regra_curta="Abertos com SlaDataSolucao &lt; Agora (BRT) e SLA ativo (SlaSolucaoPausado = 0 e PausaSla = 0).",
        o_que_e="Quantidade de chamados abertos cujo prazo contratual de solução (SLA) já expirou e continua correndo.",
        como_ler="É o principal indicador de dor imediata (no exemplo, 8 chamados em atraso). Diferente de painéis estáticos, chamados cujo status pausa SLA (como <em>Aguardando</em>) não inflam este contador; portanto, todo número maior que zero exige atenção direta.",
        acao_sugerida="Se for maior que 0, desça imediatamente para o <strong>Radar Preditivo de SLA (item 7)</strong>, filtre <code>OrdemGravidade = 1</code>, cobre atualização no Movidesk em até 30 minutos e negocie previsão formal com o cliente nos casos críticos.",
    )
    kpi_3 = render_kpi_card(
        num="03",
        title="KPI - SLA Iminente (< 4h)",
        img_filename="dash_03_kpi_sla_iminente.png",
        dataset_pill="vw_VisaoGeralKpis · SUM(SlaIminente4h)",
        regra_curta="Abertos não pausados que vencem entre Agora e +4h (parametrizável em ctl.Parametro).",
        o_que_e="Alerta antecipado de chamados abertos cujo SLA vai estourar dentro das próximas 4 horas úteis/corridas.",
        como_ler="Funciona como o &ldquo;sinal amarelo&rdquo; preventivo da Sala de Guerra. Enquanto o KPI 2 mostra o incêndio já aceso, este card indica os tickets que ainda podem ser salvos dentro do prazo antes de mancharem o SLA do cliente.",
        acao_sugerida="Sempre que exibir <strong>1 ou mais</strong>, interrompa o fluxo normal de fila e direcione um analista sênior para atuar primeiro nestes IDs (<code>OrdemGravidade</code> 2 e 3 no Radar SLA), evitando que migrem para o card de Vencidos.",
    )

    p2 = f"""
    <div class="chapter-header">
        <div class="chapter-badge">BLOCO 1 &bull; Saúde Imediata</div>
        <div class="chapter-title-block">
            <h2>Big Numbers (1 a 3): Pressão Atual da Fila e Risco de SLA</h2>
            <span>Leitura matinal obrigatória &mdash; indica volume represado, atrasos reais e prazos prestes a estourar</span>
        </div>
    </div>
    {kpi_1}
    {kpi_2}
    {kpi_3}
    <div class="callout-navy">
        <strong>Dica de Interpretação Rápida:</strong> Leia os três cards sempre como um trio contínuo: <strong>SLA Iminente (03)</strong> é o preventivo, <strong>SLA Vencidos (02)</strong> é a emergência ativa e <strong>Backlog Atual (01)</strong> é o peso total da carteira aberta. Um backlog estável com Vencidos = 0 significa fila sob controle.
    </div>
    """
    pages.append(p2)

    # =========================================================================
    # PÁGINA 3: BLOCO 1 (PARTE 2) — KPIs 4, 5, 6 + SEMÁFORO MATINAL
    # =========================================================================
    kpi_4 = render_kpi_card(
        num="04",
        title="KPI - Abertos Hoje",
        img_filename="dash_04_kpi_abertos_hoje.png",
        dataset_pill="vw_VisaoGeralKpis · SUM(AbertosHoje)",
        regra_curta="Tickets com CAST(DataCriacao AS DATE) = Hoje (Horário de Brasília).",
        o_que_e="Volume de novos chamados que entraram na fila da equipe desde a 00h00 do dia corrente (BRT).",
        como_ler="Mede a pressão de demanda do dia em tempo quase real (atualização a cada 60s após sincronismo do Control Panel). Picos anormais pela manhã costumam sinalizar incidente generalizado, indisponibilidade de serviço ou efeito colateral de deploy/virada de versão.",
        acao_sugerida="Se o volume do dia superar em +40% a média histórica da manhã, verifique no <strong>Mapa de Demanda (item 12)</strong> se há repetição de Cliente ou Serviço e dispare comunicado preventivo ou war room de incidente antes de travar a fila.",
    )
    kpi_5 = render_kpi_card(
        num="05",
        title="KPI - Resolvidos Hoje",
        img_filename="dash_05_kpi_resolvidos_hoje.png",
        dataset_pill="vw_VisaoGeralKpis · SUM(ResolvidosHoje)",
        regra_curta="Tickets cuja DataResolucao corresponde à data atual (BRT).",
        o_que_e="Quantidade de chamados efetivamente solucionados pela equipe desde o início do expediente de hoje.",
        como_ler="Deve ser lido lado a lado com <strong>Abertos Hoje (04)</strong>. Se <code>Resolvidos Hoje &ge; Abertos Hoje</code> ao fim da tarde, a equipe deu vazão e reduziu backlog; se ficar consistentemente abaixo por vários dias, a fila está envelhecendo.",
        acao_sugerida="Ao meio-dia e às 16h, compare Abertos vs Resolvidos: se a saída estiver muito abaixo da entrada sem motivo de incidente complexo, identifique gargalos de validação técnica ou pacotes parados aguardando aprovação de coordenação.",
    )
    kpi_6 = render_kpi_card(
        num="06",
        title="KPI - FCR 30 Dias (%)",
        img_filename="dash_06_kpi_fcr_30d.png",
        dataset_pill="vw_VisaoGeralKpis · AVG(FcrUltimos30DiasPct)",
        regra_curta="Resolvidos nos últimos 30 dias com flag ResolvidoPrimeiroContato = 1 dividido pelo total resolvido.",
        o_que_e="Percentual de chamados solucionados definitivamente no primeiro contato (<em>First Contact Resolution</em>) nos últimos 30 dias.",
        como_ler="Reflete maturidade técnica, base de conhecimento e clareza na triagem inicial. <strong>Atenção:</strong> caso o Movidesk não utilize a marcação nativa de FCR em todos os fluxos, ou quando a maioria das demandas exige N2/Desenvolvimento, este índice aparecerá próximo a <code>0.0</code>.",
        acao_sugerida="Se estiver caindo ou zerado quando deveria pontuar, audite se o campo FCR está preenchido corretamente pelos analistas no encerramento e crie artigos/macros de resposta rápida para dúvidas recorrentes identificadas no Mapa de Demanda.",
    )

    p3 = f"""
    <div class="chapter-header">
        <div class="chapter-badge">BLOCO 1 &bull; Saúde Imediata</div>
        <div class="chapter-title-block">
            <h2>Big Numbers (4 a 6): Ritmo do Dia, FCR e Semáforo Executivo</h2>
            <span>Balanço de produtividade diária e diagnóstico combinado para a reunião de 5 minutos</span>
        </div>
    </div>
    {kpi_4}
    {kpi_5}
    {kpi_6}
    <div class="section-heading-gold">
        <h2>Quadro Semáforo: Como Diagnosticar o Bloco 1 em Conjunto</h2>
        <div class="gold-line"></div>
    </div>
    <table class="zebra-table">
        <thead>
            <tr>
                <th style="width:27%;">Cenário Combinado no Topo</th>
                <th style="width:16%;">Diagnóstico</th>
                <th>Decisão Imediata do Coordenador / Gestor</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>Vencidos = 0</strong> e <strong>Iminente = 0</strong> e <strong>Resolvidos &ge; Abertos</strong></td>
                <td><span class="pill-green">OPERAÇÃO SAUDÁVEL</span></td>
                <td>Aproveite a folga operacional para zerar tickets envelhecidos (+48h sem ação) e revisar clientes silenciosos no Bloco 4.</td>
            </tr>
            <tr>
                <td><strong>Vencidos = 0</strong>, mas <strong>Iminente &gt; 0</strong></td>
                <td><span class="pill-amber">RISCO IMINENTE</span></td>
                <td>Atue preventivamente no Radar SLA (item 7) antes da janela de 4 horas expirar; priorize desbloqueio imediato.</td>
            </tr>
            <tr>
                <td><strong>Vencidos &gt; 0</strong> e <strong>Abertos &gt; Resolvidos</strong></td>
                <td><span class="pill-red">CRISE DE VAZÃO</span></td>
                <td>Fila acumulando sob pressão de SLA. Acione plano de contingência: redistribua tickets N1/N2 e comunique clientes críticos.</td>
            </tr>
        </tbody>
    </table>
    """
    pages.append(p3)

    # =========================================================================
    # PÁGINA 4: BLOCO 2 (PARTE 1) — RADAR SLA + EVOLUÇÃO 90 DIAS
    # =========================================================================
    radar_table = """
    <table class="zebra-table compact" style="margin-top:0.4mm;">
        <thead>
            <tr>
                <th style="width:9%;">Ordem</th>
                <th style="width:22%;">FaixaRiscoSla</th>
                <th style="width:29%;">Critério Automático da View</th>
                <th>Postura Obrigatória da Equipe</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>1</strong></td>
                <td><span class="pill-red">Vencido</span></td>
                <td><code>MinutosParaVencer &lt; 0</code> (expirado)</td>
                <td><strong>Máxima prioridade:</strong> cobrar tratativa imediata, explicar prazo ao cliente e zerar primeiro.</td>
            </tr>
            <tr>
                <td><strong>2</strong></td>
                <td><span class="pill-red">Crítico (&lt; 2h)</span></td>
                <td>Faltam até <strong>120 min</strong> para vencer</td>
                <td>Direcionar analista disponível agora para resolver ou solicitar evidência válida (pausa SLA).</td>
            </tr>
            <tr>
                <td><strong>3</strong></td>
                <td><span class="pill-amber">Alerta (&lt; 4h)</span></td>
                <td>Entre <strong>121 e 240 min</strong> (4h)</td>
                <td>Monitoramento de hora em hora na coordenação; validar se não está parado sem analista.</td>
            </tr>
            <tr>
                <td><strong>4</strong></td>
                <td><span class="pill-amber">Atenção (&lt; 8h)</span></td>
                <td>Vence no próximo turno (<strong>4h a 8h</strong>)</td>
                <td>Planejar fila da tarde / manhã seguinte para não virar alerta no dia posterior.</td>
            </tr>
            <tr>
                <td><strong>5 / 6 / 7</strong></td>
                <td><span class="pill-slate">Pausado / Sem SLA / Prazo</span></td>
                <td>5=Pausado &bull; 6=Sem Acordo &bull; 7=&gt; 8h</td>
                <td>Ordem 5 exige follow-up com o cliente; Ordem 6 precisa de revisão de acordo se aplicável.</td>
            </tr>
        </tbody>
    </table>
    """

    comp_7 = render_wide_component(
        num="07",
        title="Radar Preditivo de SLA (Fila Viva)",
        img_filename="dash_07_radar_preditivo_sla.png",
        caption="Captura real (Dashboard Movidesk BI) — Fila ativa ordenada automaticamente por OrdemGravidade (1 a 7) e MinutosParaVencer.",
        dataset_pill="vw_SlaRadar · 129 itens",
        o_que_e="Lista viva de todos os chamados em aberto ranqueados do risco de SLA mais grave para o mais seguro.",
        como_ler="Nasce ordenada por <code>OrdemGravidade ASC</code> e <code>MinutosParaVencer ASC</code>: quanto <strong>mais negativo</strong> o minuto (ex.: <code>-53225</code> no ticket <code>46182</code>), maior o atraso. A coluna <code>HorasSemInteracao</code> à direita denuncia tickets críticos abandonados sem ação (ex.: 283h a 937h).",
        acao_sugerida="Trabalhe <strong>de cima para baixo</strong> no daily matinal: primeiro atribua linhas <em>&ldquo;Não Atribuído&rdquo;</em> em gravidade 1–3; em seguida cobre tratativa imediata nos chamados <em>Ordem 1</em> com alto <code>HorasSemInteracao</code>.",
        img_max_height="22mm",
        extra_html=radar_table,
    )

    comp_8 = render_wide_component(
        num="08",
        title="Evolução Diária do Backlog e SLA Vencido (90 Dias)",
        img_filename="dash_08_evolucao_backlog_90d.png",
        caption="Captura real — Curva histórica em “montanhas” do Backlog Total (ciano) contra SLA Vencido (base grafite).",
        dataset_pill="vw_BacklogEvolucao · Snapshot",
        o_que_e="Fotografia histórica de fechamento diário mostrando a altura total do backlog e quantos estavam vencidos em cada data.",
        como_ler="Leia as &ldquo;montanhas&rdquo; em <strong>3 sinais</strong>: (1) <strong>Curva ciano subindo:</strong> indica fila crescendo acima da entrega; degrau de queda revela mutirão/fechamento em lote; (2) <strong>Faixa grafite na base:</strong> quanto mais rente ao zero, mais saudável &mdash; se descolar e acompanhar a curva (ex.: após 15/out), há atraso crônico; (3) <strong>Platô horizontal alto:</strong> equipe empata entrada e saída sem reduzir o passivo antigo.",
        acao_sugerida="Se a linha ciano subir por mais de 2 semanas ou a sombra de <strong>SLA Vencido</strong> alargar na base, dimensione déficit de capacidade, ative encerramento automático por inatividade e reporte necessidade de reforço à diretoria.",
        img_max_height="29mm",
    )

    p4 = f"""
    <div class="chapter-header">
        <div class="chapter-badge">BLOCO 2 &bull; Fila e Vazão</div>
        <div class="chapter-title-block">
            <h2>Monitoramento Preditivo e Tendência Histórica (90 Dias)</h2>
            <span>Onde atuar primeiro agora (Radar SLA) e para onde o estoque da fila está caminhando</span>
        </div>
    </div>
    {comp_7}
    {comp_8}
    """
    pages.append(p4)

    # =========================================================================
    # PÁGINA 5: BLOCO 2 (PARTE 2) + BLOCO 3 (PARTE 1) — THROUGHPUT & AGING
    # =========================================================================
    comp_9 = render_wide_component(
        num="09",
        title="Throughput Diário: Abertos vs Resolvidos",
        img_filename="dash_09_throughput_diario.png",
        caption="Captura real — Barras verticais diárias comparando entrada (Abertos, em ciano) versus vazão (Resolvidos, em grafite/azul-escuro).",
        dataset_pill="vw_ThroughputDiario",
        o_que_e="Comparativo diário entre a quantidade de chamados abertos e a quantidade de chamados resolvidos pela equipe.",
        como_ler="Observe dia a dia qual barra vence em altura: quando a barra de <strong>Resolvidos (grafite)</strong> ultrapassa a de <strong>Abertos (ciano)</strong>, dizemos que a equipe <strong>&ldquo;queimou fila&rdquo;</strong> (<code>SaldoLiquido &gt; 0</code>, reduzindo backlog real). Quando a barra <strong>ciano</strong> supera sistematicamente a grafite, a equipe <strong>acumulou backlog</strong> naquele dia/semana &mdash; sinal claro de que as entregas não acompanharam o ritmo de chegada.",
        acao_sugerida="Se houver 5 dias úteis seguidos de acúmulo (barras ciano dominando), audite o motivo: houve excesso de bugs pós-release, ausências na equipe ou retenção de tickets com o time de Produto/Desenvolvimento? Reequilibre a alocação antes que a montanha do item 8 cresça.",
        img_max_height="37mm",
    )

    comp_10 = render_wide_component(
        num="10",
        title="Auditoria de Envelhecimento (Backlog Aging & +48h Sem Ação)",
        img_filename="dash_10_auditoria_envelhecimento.png",
        caption="Captura real — Fila em aberto ordenada do maior DiasAberto ao menor, destacando HorasDesdeUltimaAcao e alerta SemInteracaoMais48h.",
        dataset_pill="vw_BacklogAging · +48h",
        o_que_e="Lista de auditoria para localizar chamados antigos em aberto e flagrar aqueles que estão parados há mais de 48 horas sem movimentação.",
        como_ler="Ordenada por <code>DiasAberto DESC</code>, mostra logo no topo o passivo histórico (ex.: 1.054 dias no topo da tabela, classificado em <code>FaixaIdade = Mais de 30 dias</code>). Fique atento às duas últimas colunas: <code>HorasDesdeUltimaAcao</code> quantifica o silêncio da última interação e <code>SemInteracaoMais48h = 1</code> acende o alerta binário de chamado &ldquo;esquecido&rdquo; (parado há mais de 48h, valor configurável em <code>ctl.Parametro</code>).",
        acao_sugerida="Institua uma rotina semanal de &ldquo;Desengavetamento&rdquo;: filtre <code>SemInteracaoMais48h = 1</code> por Analista, faça saneamento dos tickets cujo assunto já perdeu objeto (pedindo aceite de fechamento ao cliente) e cobre atualização imediata naqueles em posse técnica da Advice.",
        img_max_height="35mm",
        extra_html="""
        <div class="callout-gold">
            <strong>Por que &ldquo;+48h Sem Ação&rdquo; é ouro para a Coordenação?</strong> Um cliente raramente se incomoda tanto com a complexidade técnica quanto com a <em>falta de resposta</em>. Manter <code>SemInteracaoMais48h = 0</code> nos chamados em andamento reduz drasticamente escalações diretas e reclamações em comitês mensais.
        </div>
        """,
    )

    p5 = f"""
    <div class="chapter-header">
        <div class="chapter-badge">BLOCOS 2 &amp; 3 &bull; Vazão e Envelhecimento</div>
        <div class="chapter-title-block">
            <h2>Queima de Fila (Throughput) e Auditoria de Chamados Esquecidos</h2>
            <span>Entendendo o saldo líquido diário e higienizando o passivo antigo sem interação</span>
        </div>
    </div>
    {comp_9}
    {comp_10}
    """
    pages.append(p5)

    # =========================================================================
    # PÁGINA 6: BLOCO 3 (PARTE 2) — GARGALOS POR STATUS & MAPA DE DEMANDA
    # =========================================================================
    horas_callout = """
    <table class="zebra-table" style="margin-top:0.5mm;">
        <thead>
            <tr>
                <th style="width:22%;">Métrica na Tabela</th>
                <th style="width:39%;">O que Mede na Prática</th>
                <th>Como Interpretar Sem Cair em Pegadinha</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><code>HorasUteisMedias</code><br/><strong>(Horas Úteis)</strong></td>
                <td>Considera <strong>apenas a jornada comercial útil</strong> cadastrada no calendário do Movidesk.</td>
                <td>Representa o <strong>esforço/espera real em expediente</strong>. Ex.: <code>Em atendimento = 21.1h</code> (~2,5 dias úteis com o analista).</td>
            </tr>
            <tr>
                <td><code>HorasCorridasMedias</code><br/>e <code>Totais</code> <strong>(Corridas)</strong></td>
                <td>Conta <strong>24 horas por dia</strong>, incluindo noites, madrugadas, feriados e finais de semana.</td>
                <td>Sempre será muito maior (3x a 4x) que Horas Úteis. Em <code>Resolvido (1059.6h corridas)</code> ou <code>Aguardando (338.3h)</code>, mede o tempo total de calendário esperando aprovação/fechamento do cliente!</td>
            </tr>
        </tbody>
    </table>
    """

    comp_11 = render_wide_component(
        num="11",
        title="Gargalos Operacionais por Status (Horas Úteis e Corridas)",
        img_filename="dash_11_gargalos_status.png",
        caption="Captura real — Tempo médio e total retido em cada Status/GrupoStatus (inclui passagens concluídas e chamados ainda no status atual).",
        dataset_pill="vw_StatusAging",
        o_que_e="Raio-X de onde os tickets ficam estacionados no fluxo operacional, medindo volume de passagens e tempos úteis vs corridos.",
        como_ler="Compare sempre <code>HorasUteisMedias</code> contra <code>HorasCorridasMedias</code> no mesmo status e observe <code>QtdPassagens</code> (frequência de trânsito). No print, <code>Em atendimento</code> tem 7.842 passagens com média de apenas 21.1h úteis, mas <code>Aguardando</code> retém 136.7h úteis e <code>Resolvido (Aguardando Fechamento)</code> acumula 247.1h úteis / 1.059.6h corridas &mdash; mostrando que o tempo de ciclo infla muito fora da mão do analista.",
        acao_sugerida="Se o gargalo maior estiver em <strong>Dependência de Terceiros / Dev</strong> ou <strong>Fila (Novo)</strong> com altas <code>HorasUteisMedias</code>, atue na triagem e priorização de sprint. Se o volume travar em <strong>Aguardando Cliente</strong> ou <strong>Resolvido</strong>, configure régua automática de encerramento no Movidesk após 3–5 dias sem resposta.",
        img_max_height="33mm",
        extra_html=horas_callout,
    )

    comp_12 = render_wide_component(
        num="12",
        title="Mapa de Demanda por Serviço, Categoria e Versão Release",
        img_filename="dash_12_mapa_demanda.png",
        caption="Captura real — Pareto ordenado por Volumetria total, cruzando Equipe, Serviço, Categoria, Urgência, Versão (#133948) e HorasMediasResolucao.",
        dataset_pill="vw_MapaDemanda · #133948",
        o_que_e="Matriz de Pareto que mostra exatamente quais produtos, categorias e versões de sistema estão drenando o tempo da equipe.",
        como_ler="Olhe em sequência: <strong>1) <code>Volumetria</code></strong> identifica os campeões de volume histórico (ex.: <em>EGUARDIAN / Suporte / Média = 512</em>); <strong>2) <code>Abertos</code></strong> mostra se aquele foco continua gerando demanda hoje; <strong>3) <code>HorasMediasResolucao</code></strong> expõe quais combinações são mais caras em tempo (ex.: <em>Dúvida = 339h</em> vs <em>Crítica = 139h</em>); <strong>4) <code>VersaoProduto</code></strong> (campo #133948) revela se uma versão específica está causando onda de erros.",
        acao_sugerida="Use os 3 primeiros colocados por <code>Volumetria</code> todo fim de mês para pautar melhorias de produto com Engenharia (reduzindo bugs recorrentes), gravar tutoriais/FAQs de autoatendimento para a categoria <em>Dúvida</em> e planejar atualização de clientes presos em releases antigas.",
        img_max_height="33mm",
    )

    p6 = f"""
    <div class="chapter-header">
        <div class="chapter-badge">BLOCO 3 &bull; Eficiência e Gargalos</div>
        <div class="chapter-title-block">
            <h2>Auditoria de Fluxo (Horas Úteis vs Corridas) e Drenos de Tempo</h2>
            <span>Identificando onde o chamado estaciona e quais produtos/categorias consomem a equipe</span>
        </div>
    </div>
    {comp_11}
    {comp_12}
    """
    pages.append(p6)

    # =========================================================================
    # PÁGINA 7: BLOCO 4 (PARTE 1) — RAIO-X DE CLIENTES & RADAR DE CHURN
    # =========================================================================
    churn_rules_html = """
    <div class="callout-navy" style="margin-top:0.8mm;">
        <strong>Entendendo as Duas Regras de Negócio do Raio-X (Atualizado em Nov/2026):</strong><br/>
        <strong>1. Granularidade <code>Cliente + Serviço</code> &amp; &ldquo;Dono Atual&rdquo;:</strong> Como o mesmo banco utiliza múltiplos módulos (<em>EGUARDIAN</em>, <em>AQUILLA</em>, <em>CCS</em>), a view isola cada par <code>Cliente + Servico</code> e define como <code>Equipe</code> responsável a equipe que atendeu o <strong>último ticket aberto</strong> daquele produto.<br/>
        <strong>2. Critério &ldquo;Silencioso &gt; 60d&rdquo;:</strong> Em B2B Compliance, cliente que não abre chamado há mais de 60 dias não significa necessariamente &ldquo;tudo perfeito&rdquo; &mdash; frequentemente sinaliza <strong>subutilização do sistema, perda de patrocínio ou risco de Churn silencioso</strong>.
    </div>
    <table class="zebra-table" style="margin-top:0.8mm;">
        <thead>
            <tr>
                <th style="width:27%;">StatusRelacionamento</th>
                <th style="width:19%;">Faixa de Silêncio</th>
                <th>Leitura Executiva &amp; Cruzamento com SLA Cumprido (%)</th>
                <th style="width:28%;">Ação Recomendada (CS / Gestão)</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><span class="pill-red">Risco Churn (Silencioso &gt; 60d)</span></td>
                <td><code>&ge; 60 dias</code> sem ticket (ou nunca abriu)</td>
                <td>Conta fora do radar operacional (ex.: <em>It&rsquo;s Pay / EGUARDIAN: 1.248 dias</em>). Se vier acompanhado de <code>SLA Cumprido (%)</code> baixo (ex.: 69%), o desgaste anterior pode ter causado abandono.</td>
                <td>Agendar reunião executiva de QBR / Check-up de Saúde com CS e Gerente de Contas em até 7 dias.</td>
            </tr>
            <tr>
                <td><span class="pill-amber">Atenção (Silencioso 30-60d)</span></td>
                <td>Entre <code>30 e 59 dias</code> sem ticket</td>
                <td>Zona preventiva antes de virar risco crítico de Churn.</td>
                <td>Enviar contato proativo de acompanhamento, checar aderência à última release e novas demandas regulatórias.</td>
            </tr>
            <tr>
                <td><span class="pill-green">Ativo (&lt; 30d)</span></td>
                <td><code>&lt; 30 dias</code> desde último ticket</td>
                <td>Cliente interagindo regularmente. Monitore aqui principalmente <code>Em Aberto</code> e <code>SLA Cumprido (%)</code> (&lt; 85% exige revisão de atendimento).</td>
                <td>Garantir entrega dentro do SLA e monitorar se a frequência de aberturas indica dependência ou dúvida operacional.</td>
            </tr>
        </tbody>
    </table>
    """

    comp_13 = render_wide_component(
        num="13",
        title="Raio-X de Empresas Clientes e Radar de Churn (Silenciosos > 60d)",
        img_filename="dash_13_raio_x_clientes.png",
        caption="Captura real — Saúde da carteira por Cliente + Serviço + Equipe (Dono Atual), ordenada de quem está há mais dias sem abrir chamado.",
        dataset_pill="vw_ClienteRaioX · 107 pares",
        o_que_e="Painel de Customer Success que mede a saúde, o cumprimento de SLA e o risco de cancelamento (Churn) por empresa e produto.",
        como_ler="Ordenada por <code>Dias Sem Ticket DESC</code>, traz no topo os clientes em <code>Risco Churn (Silencioso &gt; 60d)</code>. Leia cada linha como um prontuário do produto naquela empresa: quando foi o <code>DataUltimoTicket</code>, quantos chamados gerou na história (<code>Total Tickets</code> / <code>%Total</code>), quantos tem <code>Em Aberto</code> agora e qual foi a qualidade histórica entregue (<code>SLA Cumprido (%)</code> &mdash; e no rodapé, o consolidado da equipe no <code>Summary</code>: 4.365 tickets e média de 90.2% de SLA).",
        acao_sugerida="Filtre sua <code>Equipe</code>, exporte ou anote os top 10 clientes estratégicos com <strong>&gt; 60 dias silenciosos</strong> toda segunda-feira para contato proativo de CS, e crie plano de recuperação de confiança para qualquer conta ativa com <code>SLA Cumprido (%) &lt; 85%</code>.",
        img_max_height="39mm",
        extra_html=churn_rules_html,
    )

    p7 = f"""
    <div class="chapter-header">
        <div class="chapter-badge">BLOCO 4 &bull; Sucesso do Cliente</div>
        <div class="chapter-title-block">
            <h2>Raio-X de Empresas Clientes e Radar de Churn Silencioso</h2>
            <span>Prevenindo cancelamentos antes que o cliente desapareça e medindo SLA entregue por produto</span>
        </div>
    </div>
    {comp_13}
    """
    pages.append(p7)

    # =========================================================================
    # PÁGINA 8: BLOCO 4 (PARTE 2) — DONUT + GRID CLIENTES + CADÊNCIA FINAL
    # =========================================================================
    comp_14 = render_wide_component(
        num="14",
        title="Gráfico Donut: Tickets Abertos por Cliente (Organização)",
        img_filename="dash_14_donut_clientes.png",
        caption="Captura real — Distribuição em rosca por Cliente + Serviço no período selecionado (padrão: Este mês), respeitando Equipe e Serviço.",
        dataset_pill="vw_TicketsPorClientePeriodo · Donut",
        o_que_e="Gráfico visual de fatias mostrando quais pares Cliente + Serviço concentram os chamados abertos no período escolhido.",
        como_ler="O centro da rosca exibe o volume consolidado do período dentro do filtro (ex.: <code>Total: 48</code>). As fatias identificam cada organização junto com seu produto (ex.: <em>Banco Travelex, AQUILLA = 14.59%</em> e <em>Ativa Investimentos, EGUARDIAN = 14.59%</em>) para nunca misturar produtos de outras equipes. Use as setas <code>1/3</code> abaixo da legenda à esquerda para paginar clientes menores.",
        acao_sugerida="Se apenas 2 ou 3 clientes estiverem concentrando mais de <strong>40% das fatias</strong> no mês, investigue o motivo dessa hiperdemanda (implantação recente, erro recorrente de ambiente ou falta de treinamento dos usuários) e estruture um acompanhamento dedicado para aliviar a fila.",
        img_max_height="35mm",
    )

    comp_15 = render_wide_component(
        num="15",
        title="Grid: Detalhamento de Tickets por Cliente no Período",
        img_filename="dash_15_grid_clientes_periodo.png",
        caption="Captura real — Ranking exato de Qtd Tickets, %Total e linha Summary (48) espelhando o gráfico Donut por Cliente e Serviço.",
        dataset_pill="vw_TicketsPorClientePeriodo · Grid",
        o_que_e="Tabela complementar do Donut que exibe em números exatos a quantidade e a participação (%) de cada Cliente + Serviço no período.",
        como_ler="Elimina qualquer ambiguidade de visualização das fatias menores do Donut. Mostra lado a lado <code>Cliente</code>, <code>Servico</code>, <code>Qtd Tickets</code> com barra proporcional (ex.: <em>Banco Travelex | AQUILLA | 7</em>), <code>%Total</code> (<code>14.6%</code>) e o totalizador <code>Summary = 48</code> no rodapé. Permite busca rápida pelo nome do banco na caixa <em>Search</em> no canto superior direito.",
        acao_sugerida="Use este Grid para prestar contas em reuniões mensais com clientes ofensores (mostrando volume exato e % da capacidade absorvida), justificar necessidade de pacotes de treinamento ou consultoria e conferir no <em>Summary</em> se o filtro global de <code>Período</code> e <code>Equipe</code> está coerente com o fechamento.",
        img_max_height="34mm",
    )

    cadencia_footer = """
    <div class="callout-gold" style="margin-top:0.5mm;">
        <strong>Cadência Recomendada de Governança (Checklist da Gestão Advice):</strong><br/>
        &bull; <strong>Diário (09h00 &mdash; 5 min):</strong> Validar Bloco 1 (KPIs 1–6) + zerar urgências de <code>OrdemGravidade</code> 1 e 2 no Radar SLA (item 7) + checar ritmo Abertos vs Resolvidos.<br/>
        &bull; <strong>Semanal (Segundas &mdash; 20 min):</strong> Auditar +48h Sem Ação (item 10), tendência de 90 dias (item 8) e top silenciosos &gt; 60d no Raio-X de Churn (item 13).<br/>
        &bull; <strong>Mensal (Comitê Gerencial):</strong> Cruzar Gargalos por Status (Horas Úteis &times; Corridas, item 11), Mapa de Demanda (item 12) e Ofensores no Período (itens 14–15).
    </div>
    """

    p8 = f"""
    <div class="chapter-header">
        <div class="chapter-badge">BLOCO 4 &bull; Clientes no Período</div>
        <div class="chapter-title-block">
            <h2>Concentração de Demanda por Cliente e Cadência Executiva</h2>
            <span>Detectando clientes ofensores por organização/serviço no período filtrado</span>
        </div>
    </div>
    {comp_14}
    {comp_15}
    {cadencia_footer}
    """
    pages.append(p8)

    return pages


def generate_html_document() -> str:
    """Monta o documento HTML completo com todas as páginas numeradas."""
    raw_pages = build_pages()
    total = len(raw_pages)
    rendered_pages = "\n".join(
        render_page(content, idx, total) for idx, content in enumerate(raw_pages, start=1)
    )
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{html.escape(MANUAL_TITLE_HEADER)}</title>
    <style>
{CSS_STYLES}
    </style>
</head>
<body>
{rendered_pages}
</body>
</html>
"""


def find_browser_fallback() -> Optional[str]:
    """Localiza Chrome/Edge/Chromium caso WeasyPrint não esteja disponível."""
    candidates = [
        "google-chrome",
        "chromium",
        "chromium-browser",
        "msedge",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for item in candidates:
        found = shutil.which(item)
        if found:
            return found
        if Path(item).exists():
            return item
    return None


def export_pdf(html_path: Path, pdf_path: Path) -> str:
    """Gera o PDF prioritariamente com WeasyPrint, com fallback automático para Chromium/Edge."""
    try:
        import weasyprint  # type: ignore

        weasyprint.HTML(filename=str(html_path)).write_pdf(str(pdf_path))
        return "WeasyPrint"
    except ImportError as exc:
        print(f"[AVISO] WeasyPrint não instalado ({exc}). Tentando fallback de navegador headless...")
    except Exception as exc:
        print(f"[AVISO] Falha no WeasyPrint ({exc}). Tentando fallback de navegador headless...")

    browser = find_browser_fallback()
    if not browser:
        raise RuntimeError(
            "Nem WeasyPrint nem Chrome/Edge headless estão disponíveis neste ambiente.\n"
            "Instale o WeasyPrint com: pip install weasyprint"
        )

    cmd = [
        browser,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--print-to-pdf-no-header",
        f"--print-to-pdf={pdf_path}",
        html_path.resolve().as_uri(),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0 or not pdf_path.exists():
        raise RuntimeError(f"Falha ao gerar PDF via {browser}: {res.stderr}")
    return f"Browser Headless ({Path(browser).name})"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gera o Manual Executivo de Leitura — Dashboard Movidesk BI em HTML e PDF."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BASE_DIR,
        help="Diretório de saída para .html e .pdf (padrão: docs/manuais).",
    )
    parser.add_argument(
        "--odt",
        type=Path,
        default=None,
        help="Caminho opcional para Prints_Dashboard.odt caso assets/ precise ser populado.",
    )
    args = parser.parse_args()

    out_dir: Path = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"{OUTPUT_BASENAME}.html"
    pdf_path = out_dir / f"{OUTPUT_BASENAME}.pdf"

    ensure_assets(args.odt)
    full_html = generate_html_document()
    html_path.write_text(full_html, encoding="utf-8")
    print(f"[OK] HTML gerado em: {html_path} ({html_path.stat().st_size:,} bytes)")

    engine = export_pdf(html_path, pdf_path)
    print(f"[OK] PDF gerado via {engine}: {pdf_path} ({pdf_path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
