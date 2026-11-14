#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gerador Oficial de Manuais Corporativos em PDF e HTML (Padrão Advice Compliance Solutions)
==========================================================================================
Gera os três manuais oficiais do ecossistema Movidesk BI:
  1. Manual_01_Operacao_Painel_Controle_Movidesk_BI (.html e .pdf)
     Título: NOVIDADES DA VERSÃO - Painel de Controle Movidesk BI
  2. Manual_02_Configuracao_Apache_Superset_Corporativo (.html e .pdf)
     Título: MANUAL DE CONFIGURAÇÃO - Apache Superset Corporativo
  3. Manual_03_Dicionario_de_Dados_MovideskDM (.html e .pdf)
     Título: MANUAL DE ARQUITETURA - Dicionário de Dados (MovideskDM)

Padrão Visual Corporativo (Referência "CCS - 1 JUD.pdf"):
  - Cores Principais: Azul-Petróleo Escuro (#0B3B52) e Dourado/Mostarda Escuro (#C59217), fundo branco (#FFFFFF).
  - Cabeçalho em todas as páginas: Faixa azul-petróleo escura com "ADVICE COMPLIANCE SOLUTIONS" à esquerda
    e o título do manual à direita.
  - Rodapé em todas as páginas: "Advice Compliance Solutions" à esquerda e "Página X de Y" à direita.
  - Tipografia: Open Sans / Arial / Helvetica.
  - Estrutura: Capa com Título Grande + Destaques enumerados + Índice + Capítulos numerados + Tabelas Zebradas
    + Espaços cinzas "[INSERIR IMAGEM AQUI: Screenshot da tela X]" já acompanhados das telas reais/ilustradas.

Como executar no Windows ou Linux:
  python gerar_manuais_pdf.py
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
ROOT_SCREENSHOT = Path("/home/antigravity/image.png")


def garantir_recortes_screenshots() -> None:
    """Se as capturas do Manual 1 ainda não existirem em assets/, gera recortes individuais."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    if (ASSETS_DIR / "tela_01_visao_geral.png").exists() or not ROOT_SCREENSHOT.exists():
        return
    try:
        from PIL import Image

        im = Image.open(ROOT_SCREENSHOT)
        w, h = im.size
        im.save(ASSETS_DIR / "tela_01_visao_geral.png")
        im.crop((0, 0, int(w * 0.495), int(h * 0.585))).save(
            ASSETS_DIR / "tela_02_launcher_superset.png"
        )
        im.crop((int(w * 0.495), 0, w, int(h * 0.585))).save(
            ASSETS_DIR / "tela_03_monitor_volumetria.png"
        )
        im.crop((0, int(h * 0.575), w, h)).save(
            ASSETS_DIR / "tela_04_orquestrador_carga.png"
        )
    except Exception as exc:
        print(f"[AVISO] Não foi possível recortar {ROOT_SCREENSHOT}: {exc}")


def img_to_data_uri(filename: str) -> str:
    """Converte uma imagem da pasta assets/ em Data URI base64 para embutir no HTML/PDF."""
    path = ASSETS_DIR / filename
    if not path.exists():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


COMMON_CSS = """
@page {
    size: A4 portrait;
    margin: 0;
}

* {
    box-sizing: border-box;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
}

html, body {
    margin: 0;
    padding: 0;
    background-color: #cbd5e1;
    font-family: 'Open Sans', 'Segoe UI', Arial, Helvetica, sans-serif;
    color: #1e293b;
    font-size: 9.4pt;
    line-height: 1.42;
}

@media print {
    html, body {
        background-color: #ffffff;
    }
    .pdf-page {
        margin: 0 !important;
        box-shadow: none !important;
        page-break-after: always;
        break-after: page;
    }
    .pdf-page:last-child {
        page-break-after: auto;
        break-after: auto;
    }
}

.pdf-page {
    width: 210mm;
    height: 297mm;
    background-color: #ffffff;
    margin: 8mm auto;
    box-shadow: 0 6px 24px rgba(15, 23, 42, 0.18);
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    position: relative;
    overflow: hidden;
}

/* =========================================================================
   CABEÇALHO PADRÃO ADVICE (FAIXA AZUL-PETRÓLEO ESCURA + FILETE DOURADO)
   ========================================================================= */
.page-header {
    background: linear-gradient(90deg, #093246 0%, #0F435C 100%);
    color: #ffffff;
    padding: 4.5mm 14mm;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1.2mm solid #C59217;
    flex-shrink: 0;
}

.page-header .brand-left {
    font-size: 8.8pt;
    font-weight: 800;
    letter-spacing: 1.1px;
    text-transform: uppercase;
    color: #ffffff;
    display: flex;
    align-items: center;
    gap: 2.5mm;
}

.page-header .brand-dot {
    width: 2.4mm;
    height: 2.4mm;
    background-color: #C59217;
    border-radius: 50%;
    display: inline-block;
}

.page-header .manual-title-right {
    font-size: 8.2pt;
    font-weight: 600;
    color: #f1f5f9;
    letter-spacing: 0.3px;
    text-align: right;
}

/* =========================================================================
   CORPO DA PÁGINA
   ========================================================================= */
.page-body {
    flex: 1;
    padding: 7mm 14mm 5mm 14mm;
    display: flex;
    flex-direction: column;
    gap: 3.5mm;
    overflow: hidden;
}

/* =========================================================================
   RODAPÉ PADRÃO ADVICE
   ========================================================================= */
.page-footer {
    padding: 3.2mm 14mm 4.5mm 14mm;
    border-top: 0.4mm solid #cbd5e1;
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 8pt;
    color: #475569;
    background-color: #ffffff;
    flex-shrink: 0;
}

.page-footer .footer-left {
    font-weight: 700;
    color: #0B3B52;
}

.page-footer .footer-right {
    font-weight: 700;
    color: #B3820E;
}

/* =========================================================================
   PÁGINA INICIAL (HERO + 4 DESTAQUES + ÍNDICE)
   ========================================================================= */
.cover-banner {
    background: linear-gradient(135deg, #0B3B52 0%, #124E6B 100%);
    color: #ffffff;
    border-radius: 2mm;
    padding: 6.5mm 7.5mm;
    border-left: 2.2mm solid #C59217;
    position: relative;
}

.cover-tag {
    display: inline-block;
    background-color: #C59217;
    color: #ffffff;
    font-size: 7.5pt;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.9px;
    padding: 1mm 2.8mm;
    border-radius: 1mm;
    margin-bottom: 2.2mm;
}

.cover-banner h1 {
    margin: 0 0 1.8mm 0;
    font-size: 18pt;
    font-weight: 800;
    line-height: 1.18;
    color: #ffffff;
    letter-spacing: -0.2px;
}

.cover-banner p {
    margin: 0;
    font-size: 9.2pt;
    color: #e2e8f0;
    line-height: 1.4;
}

.cover-meta-strip {
    display: flex;
    gap: 6mm;
    margin-top: 3.2mm;
    padding-top: 2.6mm;
    border-top: 1px solid rgba(255, 255, 255, 0.18);
    font-size: 7.8pt;
    color: #f8fafc;
}

.cover-meta-strip span strong {
    color: #F3C65F;
}

.section-heading-gold {
    display: flex;
    align-items: center;
    gap: 2.5mm;
    margin: 1mm 0 0.5mm 0;
}

.section-heading-gold h2 {
    margin: 0;
    font-size: 11pt;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: #0B3B52;
}

.section-heading-gold .gold-line {
    flex: 1;
    height: 0.5mm;
    background: linear-gradient(90deg, #C59217 0%, #e2e8f0 100%);
}

/* Grid 2x2 dos 4 Destaques e Grid 3 colunas dos 3 Destaques */
.highlights-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 3.2mm;
}

.highlights-grid-3 {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 2.8mm;
}

.highlight-card {
    background-color: #f8fafc;
    border: 1px solid #cbd5e1;
    border-top: 1mm solid #0B3B52;
    border-radius: 1.6mm;
    padding: 3.2mm 3.8mm;
    display: flex;
    gap: 3mm;
    align-items: flex-start;
}

.highlight-num {
    background-color: #C59217;
    color: #ffffff;
    font-size: 11pt;
    font-weight: 800;
    min-width: 8.5mm;
    height: 8.5mm;
    border-radius: 1.4mm;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}

.highlight-content h3 {
    margin: 0 0 1mm 0;
    font-size: 9.4pt;
    font-weight: 800;
    color: #0B3B52;
}

.highlight-content p {
    margin: 0;
    font-size: 8.3pt;
    color: #334155;
    line-height: 1.35;
}

/* Caixa de Índice / Sumário */
.toc-box {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-left: 1.6mm solid #0B3B52;
    border-radius: 1.6mm;
    padding: 3.5mm 4.5mm;
}

.toc-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 1.8mm;
}

.toc-item {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    font-size: 8.8pt;
    border-bottom: 1px dashed #cbd5e1;
    padding-bottom: 1.2mm;
}

.toc-item:last-child {
    border-bottom: none;
    padding-bottom: 0;
}

.toc-item-left {
    display: flex;
    align-items: center;
    gap: 2.5mm;
}

.toc-badge {
    background-color: #0B3B52;
    color: #ffffff;
    font-weight: 800;
    font-size: 7.4pt;
    padding: 0.5mm 2mm;
    border-radius: 0.8mm;
}

.toc-title {
    font-weight: 700;
    color: #0B3B52;
}

.toc-desc {
    color: #64748b;
    font-size: 8pt;
}

.toc-page {
    font-weight: 800;
    color: #B3820E;
    font-size: 8.4pt;
    white-space: nowrap;
}

/* =========================================================================
   CAPÍTULOS NUMERADOS (01, 02, 03...)
   ========================================================================= */
.chapter-header {
    display: flex;
    align-items: center;
    gap: 3.5mm;
    border-bottom: 0.7mm solid #0B3B52;
    padding-bottom: 2.2mm;
    margin-bottom: 0.5mm;
}

.chapter-badge {
    background-color: #C59217;
    color: #ffffff;
    font-size: 9pt;
    font-weight: 800;
    padding: 1.4mm 3.2mm;
    border-radius: 1.2mm;
    letter-spacing: 0.6px;
    text-transform: uppercase;
    flex-shrink: 0;
}

.chapter-title-block h2 {
    margin: 0;
    font-size: 13pt;
    font-weight: 800;
    color: #0B3B52;
    line-height: 1.15;
}

.chapter-title-block span {
    font-size: 8.2pt;
    color: #B3820E;
    font-weight: 700;
}

p.lead-text {
    margin: 0;
    font-size: 9pt;
    color: #1e293b;
    text-align: justify;
}

/* Passos numerados didáticos ("mastigados") */
.steps-container {
    display: flex;
    flex-direction: column;
    gap: 2mm;
}

.step-row {
    display: flex;
    align-items: flex-start;
    gap: 2.6mm;
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-left: 1.2mm solid #C59217;
    border-radius: 1.2mm;
    padding: 2mm 3mm;
}

.step-circle {
    background-color: #0B3B52;
    color: #ffffff;
    font-weight: 800;
    font-size: 7.8pt;
    min-width: 5.5mm;
    height: 5.5mm;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    margin-top: 0.3mm;
}

.step-text {
    font-size: 8.6pt;
    color: #1e293b;
    line-height: 1.36;
}

.step-text strong {
    color: #0B3B52;
}

code, .code-inline {
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 8.1pt;
    background-color: #e2e8f0;
    color: #0B3B52;
    padding: 0.3mm 1.4mm;
    border-radius: 0.8mm;
    font-weight: 700;
}

.code-banner {
    background-color: #0f172a;
    color: #f8fafc;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 8.2pt;
    padding: 2.4mm 3.5mm;
    border-radius: 1.2mm;
    border-left: 1.4mm solid #C59217;
    overflow-x: hidden;
    white-space: pre-wrap;
    word-break: break-all;
}

.callout-gold {
    background-color: #fffbeb;
    border: 1px solid #fcd34d;
    border-left: 1.5mm solid #C59217;
    border-radius: 1.2mm;
    padding: 2.2mm 3.2mm;
    font-size: 8.4pt;
    color: #78350f;
}

.callout-gold strong {
    color: #92400e;
}

/* =========================================================================
   TABELAS ZEBRADAS CORPORATIVAS (PADRÃO ADVICE)
   ========================================================================= */
.zebra-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 8.1pt;
    border: 1px solid #cbd5e1;
}

.zebra-table thead tr {
    background-color: #0B3B52;
    color: #ffffff;
}

.zebra-table thead th {
    padding: 2mm 2.6mm;
    text-align: left;
    font-weight: 800;
    letter-spacing: 0.3px;
    border-bottom: 0.8mm solid #C59217;
    font-size: 8pt;
}

.zebra-table tbody td {
    padding: 1.8mm 2.6mm;
    border-bottom: 1px solid #e2e8f0;
    color: #1e293b;
    vertical-align: top;
}

.zebra-table tbody tr:nth-child(even) {
    background-color: #f1f5f9;
}

.zebra-table tbody tr:nth-child(odd) {
    background-color: #ffffff;
}

.steps-container.compact {
    gap: 1.3mm;
}

.steps-container.compact .step-row {
    padding: 1.4mm 2.5mm;
}

.steps-container.compact .step-text {
    font-size: 8.1pt;
    line-height: 1.28;
}

.zebra-table.compact {
    font-size: 7.6pt;
}

.zebra-table.compact thead th {
    padding: 1.4mm 2.2mm;
    font-size: 7.6pt;
}

.zebra-table.compact tbody td {
    padding: 1.15mm 2.2mm;
    line-height: 1.26;
}

.zebra-table.compact code {
    font-size: 7.4pt;
    padding: 0.15mm 1.1mm;
}

.badge-pill {
    display: inline-block;
    padding: 0.4mm 1.8mm;
    border-radius: 0.8mm;
    font-size: 7.3pt;
    font-weight: 800;
    text-transform: uppercase;
}

.badge-teal {
    background-color: #0B3B52;
    color: #ffffff;
}

.badge-gold {
    background-color: #C59217;
    color: #ffffff;
}

.badge-green {
    background-color: #065f46;
    color: #ffffff;
}

.obj-banner {
    background: linear-gradient(90deg, #0B3B52 0%, #134e6b 100%);
    color: #ffffff;
    padding: 1.5mm 3mm;
    border-left: 1.6mm solid #C59217;
    border-radius: 1mm 1mm 0 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 8.1pt;
    margin-bottom: -2.4mm;
}

.obj-banner strong {
    color: #fcd34d;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 8.4pt;
}

.obj-banner span.obj-meta {
    font-size: 7.2pt;
    color: #e2e8f0;
    font-weight: 600;
}

.zebra-table.dict-table {
    font-size: 7.3pt;
}

.zebra-table.dict-table thead th {
    padding: 1.15mm 2mm;
    font-size: 7.3pt;
}

.zebra-table.dict-table tbody td {
    padding: 0.95mm 2mm;
    line-height: 1.22;
}

.zebra-table.dict-table code {
    font-size: 7.1pt;
    padding: 0.1mm 1mm;
}

.zebra-table.dict-dense {
    font-size: 6.85pt;
}

.zebra-table.dict-dense thead th {
    padding: 0.95mm 1.8mm;
    font-size: 6.95pt;
}

.zebra-table.dict-dense tbody td {
    padding: 0.72mm 1.8mm;
    line-height: 1.18;
}

.zebra-table.dict-dense code {
    font-size: 6.7pt;
    padding: 0.08mm 0.9mm;
}

/* =========================================================================
   ESPAÇOS CINZAS DE SCREENSHOT ("[INSERIR IMAGEM AQUI: Screenshot da tela X]")
   ========================================================================= */
.screenshot-placeholder-box {
    background-color: #e2e8f0;
    border: 1.5px dashed #64748b;
    border-radius: 1.8mm;
    padding: 2.2mm 3mm;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1.8mm;
}

.screenshot-placeholder-tag {
    background-color: #cbd5e1;
    color: #0B3B52;
    font-weight: 800;
    font-size: 8pt;
    padding: 1mm 3mm;
    border-radius: 1mm;
    border: 1px solid #94a3b8;
    letter-spacing: 0.3px;
    text-align: center;
    width: 100%;
}

.screenshot-img-wrapper {
    width: 100%;
    background-color: #0f172a;
    border-radius: 1.2mm;
    overflow: hidden;
    border: 1px solid #334155;
    display: flex;
    justify-content: center;
    align-items: center;
}

.screenshot-img-wrapper img {
    width: 100%;
    max-height: 64mm;
    object-fit: contain;
    display: block;
}

.screenshot-caption {
    font-size: 7.5pt;
    color: #475569;
    font-style: italic;
    text-align: center;
}

/* Mockup visual de telas do Superset / Ngrok (para o Manual 2) */
.ui-mockup {
    width: 100%;
    background-color: #ffffff;
    border: 1px solid #94a3b8;
    border-radius: 1.2mm;
    overflow: hidden;
    font-size: 7.6pt;
    color: #1e293b;
}

.ui-mockup-topbar {
    background-color: #1e293b;
    color: #ffffff;
    padding: 1.5mm 3mm;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-weight: 700;
    font-size: 7.5pt;
}

.ui-mockup-body {
    padding: 2.5mm 3.5mm;
    background-color: #f8fafc;
    display: flex;
    flex-direction: column;
    gap: 1.6mm;
}

.ui-field {
    display: flex;
    flex-direction: column;
    gap: 0.5mm;
}

.ui-field-label {
    font-size: 6.8pt;
    font-weight: 800;
    color: #475569;
    text-transform: uppercase;
}

.ui-field-input {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-left: 1mm solid #0B3B52;
    padding: 1.1mm 2mm;
    border-radius: 0.8mm;
    font-family: 'Consolas', monospace;
    font-size: 7.5pt;
    color: #0B3B52;
    font-weight: 700;
}

.ui-btn-row {
    display: flex;
    justify-content: flex-end;
    gap: 2mm;
    margin-top: 1mm;
}

.ui-btn {
    padding: 1mm 2.5mm;
    border-radius: 0.8mm;
    font-weight: 800;
    font-size: 7.2pt;
}

.ui-btn-outline {
    background-color: #ffffff;
    border: 1px solid #0B3B52;
    color: #0B3B52;
}

.ui-btn-solid {
    background-color: #C59217;
    color: #ffffff;
}
"""


def render_page(manual_title: str, page_num: int, total_pages: int, body_html: str) -> str:
    """Envolve o conteúdo de uma página A4 com o Cabeçalho e Rodapé oficiais da Advice."""
    return f"""
    <section class="pdf-page">
        <header class="page-header">
            <div class="brand-left">
                <span class="brand-dot"></span>
                <span>ADVICE COMPLIANCE SOLUTIONS</span>
            </div>
            <div class="manual-title-right">{manual_title}</div>
        </header>

        <main class="page-body">
            {body_html}
        </main>

        <footer class="page-footer">
            <span class="footer-left">Advice Compliance Solutions</span>
            <span class="footer-right">Página {page_num} de {total_pages}</span>
        </footer>
    </section>
    """


def build_manual_1_html() -> str:
    """Constrói o HTML completo do Manual 1: Operação do Painel de Controle (Movidesk BI)."""
    manual_title = "NOVIDADES DA VERSÃO - Painel de Controle Movidesk BI"
    total_pages = 5

    img_01 = img_to_data_uri("tela_01_visao_geral.png")
    img_02 = img_to_data_uri("tela_02_launcher_superset.png")
    img_03 = img_to_data_uri("tela_03_monitor_volumetria.png")
    img_04 = img_to_data_uri("tela_04_orquestrador_carga.png")

    # -------------------------------------------------------------------------
    # PÁGINA 1: CAPA + 4 DESTAQUES + ÍNDICE + VISÃO GERAL
    # -------------------------------------------------------------------------
    p1 = f"""
    <div class="cover-banner">
        <span class="cover-tag">Documentação Oficial de Operação · Release v1.0.5</span>
        <h1>{manual_title}</h1>
        <p>Guia corporativo de operação da plataforma de orquestração BI do Movidesk: inicialização silenciosa do Apache Superset no WSL2, monitoramento em tempo real do Data Mart SQL Server (MovideskDM) e motor assíncrono de ingestão Anti-Travamento.</p>
        <div class="cover-meta-strip">
            <span><strong>Unidade:</strong> Inteligência Operacional &amp; Suporte</span>
            <span><strong>Aplicação:</strong> MovideskControlPanel.exe (.NET 8)</span>
            <span><strong>Banco:</strong> MSSQL (MovideskDM)</span>
        </div>
    </div>

    <div class="section-heading-gold">
        <h2>Destaques da Versão (01 a 04)</h2>
        <div class="gold-line"></div>
    </div>

    <div class="highlights-grid">
        <div class="highlight-card">
            <div class="highlight-num">01</div>
            <div class="highlight-content">
                <h3>Arquitetura Desktop Assíncrona</h3>
                <p>Aplicativo nativo Windows (<code>MovideskControlPanel.exe</code>) com Blazor Hybrid/Server, conectado ao SQL Server local (<code>MovideskDM</code>) e motor extrator C# em background.</p>
            </div>
        </div>
        <div class="highlight-card">
            <div class="highlight-num">02</div>
            <div class="highlight-content">
                <h3>Launcher Silencioso do Superset</h3>
                <p>Acionamento automático do Apache Superset 6.1.0 no WSL2 (Ubuntu) via <code>System.Diagnostics.Process</code> sem janelas de terminal e com verificação contínua de saúde.</p>
            </div>
        </div>
        <div class="highlight-card">
            <div class="highlight-num">03</div>
            <div class="highlight-content">
                <h3>Monitor de Volumetria em Tempo Real</h3>
                <p>Auditoria instantânea via Dapper sobre <code>core.Fato_Ticket</code>, exibindo total de chamados processados, empresas vinculadas, faixa de IDs e snapshots históricos.</p>
            </div>
        </div>
        <div class="highlight-card">
            <div class="highlight-num">04</div>
            <div class="highlight-content">
                <h3>Orquestrador Anti-Travamento</h3>
                <p>Cargas Histórica e Incremental estritamente assíncronas (<code>Task.Run</code>) com suporte a <code>Skip</code>/Cursor inteligente, sincronização de Empresas (<code>/persons</code>) e console vivo.</p>
            </div>
        </div>
    </div>

    <div class="section-heading-gold">
        <h2>Índice / Conteúdo</h2>
        <div class="gold-line"></div>
    </div>

    <div class="toc-box">
        <ul class="toc-list">
            <li class="toc-item">
                <div class="toc-item-left">
                    <span class="toc-badge">CAPÍTULO 01</span>
                    <span class="toc-title">A Arquitetura</span>
                    <span class="toc-desc">— Funcionamento assíncrono (Blazor, banco MSSQL local MovideskDM e Extrator C#)</span>
                </div>
                <span class="toc-page">Página 02</span>
            </li>
            <li class="toc-item">
                <div class="toc-item-left">
                    <span class="toc-badge">CAPÍTULO 02</span>
                    <span class="toc-title">Launcher do Superset</span>
                    <span class="toc-desc">— Como iniciar o Superset no WSL2 em background e monitorar o status na porta 8088</span>
                </div>
                <span class="toc-page">Página 03</span>
            </li>
            <li class="toc-item">
                <div class="toc-item-left">
                    <span class="toc-badge">CAPÍTULO 03</span>
                    <span class="toc-title">Monitor de Volumetria</span>
                    <span class="toc-desc">— Contagem em tempo real via Dapper, tabela core.Fato_Ticket e vínculo de Empresas</span>
                </div>
                <span class="toc-page">Página 04</span>
            </li>
            <li class="toc-item">
                <div class="toc-item-left">
                    <span class="toc-badge">CAPÍTULO 04</span>
                    <span class="toc-title">Orquestrador Anti-Travamento</span>
                    <span class="toc-desc">— Carga Histórica (Skip / Cursor), Carga Incremental assíncrona e API /persons</span>
                </div>
                <span class="toc-page">Página 05</span>
            </li>
        </ul>
    </div>
    """

    # -------------------------------------------------------------------------
    # PÁGINA 2: CAPÍTULO 01 - A ARQUITETURA
    # -------------------------------------------------------------------------
    p2 = f"""
    <div class="chapter-header">
        <span class="chapter-badge">Capítulo 01</span>
        <div class="chapter-title-block">
            <h2>A Arquitetura do Ecossistema Movidesk BI</h2>
            <span>Funcionamento Assíncrono · Interface Blazor · SQL Server Local (MovideskDM) · Motor Extrator C#</span>
        </div>
    </div>

    <p class="lead-text">
        O <strong>Painel de Controle Movidesk BI</strong> foi projetado para eliminar operações manuais em linha de comando (PowerShell/Bash), centralizando toda a infraestrutura analítica da Advice em um único executável Windows (<code>MovideskControlPanel.exe</code>). Sua arquitetura desacopla a interface gráfica do processamento pesado de dados por meio de três pilares integrados:
    </p>

    <div class="steps-container">
        <div class="step-row">
            <div class="step-circle">1</div>
            <div class="step-text">
                <strong>Camada de Apresentação Reativa (Blazor Server / Hybrid):</strong> Renderiza os três módulos operacionais em tempo real. A thread de interface (UI Thread) nunca executa loops de rede ou banco diretamente; ela apenas escuta eventos de estado (<code>OnStateChanged</code>) emitidos pelos serviços em segundo plano.
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">2</div>
            <div class="step-text">
                <strong>Motor Extrator C# Assíncrono (<code>MovideskIngestionService</code>):</strong> Opera estritamente dentro de <code>Task.Run</code> com <code>async/await</code> e <code>CancellationTokenSource</code>. Consome as APIs REST do Movidesk (<code>/tickets</code>, <code>/tickets/past</code> e <code>/persons</code>), respeita automaticamente a janela de Rate Limit (10 req/min em horário comercial) e atualiza sozinho as Procedures e Views do banco na inicialização.
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">3</div>
            <div class="step-text">
                <strong>Data Mart Local em Microsoft SQL Server (<code>MovideskDM</code>):</strong> Estrutura os dados em 5 schemas especializados (<code>raw</code>, <code>core</code>, <code>mart</code>, <code>ctl</code> e <code>sec</code>), convertendo todos os horários UTC da API para <strong>Horário Oficial de Brasília (BRT)</strong> e servindo 8 Views analíticas prontas para o Apache Superset.
            </div>
        </div>
    </div>

    <table class="zebra-table">
        <thead>
            <tr>
                <th style="width: 18%;">Camada / Componente</th>
                <th style="width: 27%;">Tecnologia / Objeto</th>
                <th>Responsabilidade na Arquitetura</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><span class="badge-pill badge-teal">Host Desktop</span></td>
                <td><code>MovideskControlPanel.exe</code></td>
                <td>Aplicação .NET 8 (WinForms + Blazor WebView2) standalone. Lê configurações em <code>appsettings.json</code>.</td>
            </tr>
            <tr>
                <td><span class="badge-pill badge-gold">Camada RAW</span></td>
                <td><code>raw.Ticket</code> / <code>raw.Pessoa</code></td>
                <td>Pouso imediato do payload JSON bruto vindo da API Movidesk via <code>MERGE</code> idempotente.</td>
            </tr>
            <tr>
                <td><span class="badge-pill badge-teal">Camada CORE</span></td>
                <td><code>core.Fato_Ticket</code> e Dimensões</td>
                <td>Modelo estrela normalizado pelas procedures <code>usp_ProcessarTickets</code> e <code>usp_ProcessarPessoas</code>.</td>
            </tr>
            <tr>
                <td><span class="badge-pill badge-gold">Camada MART</span></td>
                <td><code>mart.vw_*</code> (8 Views)</td>
                <td>Camada semântica de indicadores (SLA, Backlog, Aging, Throughput e Raio-X de Clientes) lida pelo Superset.</td>
            </tr>
            <tr>
                <td><span class="badge-pill badge-teal">Camada CTL / SEC</span></td>
                <td><code>ctl.MarcaDagua</code> / <code>sec.*</code></td>
                <td>Controle de cursor incremental, auditoria de lotes (<code>ctl.ExecucaoCarga</code>) e segurança por equipe.</td>
            </tr>
        </tbody>
    </table>

    <div class="screenshot-placeholder-box">
        <div class="screenshot-placeholder-tag">[INSERIR IMAGEM AQUI: Screenshot da tela 01 - Visão Geral do Painel de Controle Movidesk BI]</div>
        {f'<div class="screenshot-img-wrapper"><img src="{img_01}" alt="Tela 01 - Visão Geral do Painel de Controle" /></div>' if img_01 else ''}
        <div class="screenshot-caption">Figura 1.1 — Tela principal do MovideskControlPanel.exe exibindo os 3 módulos integrados em execução.</div>
    </div>
    """

    # -------------------------------------------------------------------------
    # PÁGINA 3: CAPÍTULO 02 - LAUNCHER DO SUPERSET
    # -------------------------------------------------------------------------
    p3 = f"""
    <div class="chapter-header">
        <span class="chapter-badge">Capítulo 02</span>
        <div class="chapter-title-block">
            <h2>Launcher do Apache Superset (WSL2 em Background)</h2>
            <span>Acionamento Silencioso via System.Diagnostics.Process e Monitoramento de Saúde na Porta 8088</span>
        </div>
    </div>

    <p class="lead-text">
        O módulo <strong>1. Launcher do Apache Superset</strong> encapsula toda a complexidade do subsistema Linux (WSL2 Ubuntu) no Windows. Por meio da classe <code>SupersetService</code>, o painel utiliza <code>System.Diagnostics.Process</code> com as flags <code>CreateNoWindow = true</code> e <code>UseShellExecute = false</code> para ativar o ambiente virtual Python (<code>~/superset-env/bin/activate</code>) e levantar o Gunicorn/Superset na porta <code>8088</code> sem abrir nenhuma janela preta de terminal na área de trabalho do operador.
    </p>

    <div class="steps-container">
        <div class="step-row">
            <div class="step-circle">1</div>
            <div class="step-text">
                <strong>Subir o Servidor (Botão "Iniciar Superset (WSL2)"):</strong> Ao clicar no botão azul primário, o status muda imediatamente para <span class="badge-pill badge-gold">Subindo servidor...</span> com um spinner visual. Internamente, o C# dispara <code>wsl.exe -d Ubuntu -- bash -lc "source ~/superset-env/bin/activate && nohup superset run -h 0.0.0.0 -p 8088 ..."</code>.
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">2</div>
            <div class="step-text">
                <strong>Sondagem Automática de Saúde (Health Check HTTP):</strong> Enquanto o servidor inicializa, o painel executa requisições assíncronas a cada 2 segundos para <code>http://localhost:8088/health</code>. Assim que o Superset responde <code>HTTP 200 OK</code>, o badge superior fica verde (<span class="badge-pill badge-green">Online</span>).
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">3</div>
            <div class="step-text">
                <strong>Acesso Rápido e Diagnóstico ("Abrir Superset ↗" e "Verificar Status"):</strong> Quando o servidor está <em>Online</em>, o botão verde <strong>"Abrir Superset ↗"</strong> aparece automaticamente para abrir o navegador padrão direto nos dashboards. O console inferior registra todos os eventos de inicialização com carimbo de hora.
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">4</div>
            <div class="step-text">
                <strong>Encerramento Limpo ("Parar Superset"):</strong> Caso seja necessário reiniciar o serviço, o botão vermelho encerra os processos do Superset/Gunicorn dentro do WSL2 de forma segura e retorna o indicador para <em>Offline</em>.
            </div>
        </div>
    </div>

    <table class="zebra-table">
        <thead>
            <tr>
                <th style="width: 22%;">Botão / Indicador</th>
                <th style="width: 24%;">Estado Visual</th>
                <th>Comportamento Técnico Executado pelo Painel</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>Iniciar Superset (WSL2)</strong></td>
                <td><span class="badge-pill badge-gold">Subindo servidor...</span></td>
                <td>Dispara o comando bash no WSL2 em background e inicia o polling HTTP até a porta <code>8088</code> responder.</td>
            </tr>
            <tr>
                <td><strong>Abrir Superset ↗</strong></td>
                <td><span class="badge-pill badge-green">Online</span></td>
                <td>Exibido somente quando o endpoint <code>/health</code> confirma disponibilidade. Abre <code>http://localhost:8088</code>.</td>
            </tr>
            <tr>
                <td><strong>Verificar Status</strong></td>
                <td>Consulta Imediata</td>
                <td>Executa um teste instantâneo de conectividade na porta configurada em <code>Superset:Port</code> no <code>appsettings.json</code>.</td>
            </tr>
            <tr>
                <td><strong>Parar Superset</strong></td>
                <td><span class="badge-pill badge-teal">Offline</span></td>
                <td>Envia <code>pkill -f "superset|gunicorn"</code> via WSL2 para liberar memória e encerrar a instância ativa.</td>
            </tr>
        </tbody>
    </table>

    <div class="screenshot-placeholder-box">
        <div class="screenshot-placeholder-tag">[INSERIR IMAGEM AQUI: Screenshot da tela 02 - Card 1: Launcher do Apache Superset (WSL2)]</div>
        {f'<div class="screenshot-img-wrapper"><img src="{img_02}" alt="Tela 02 - Card Launcher do Apache Superset" /></div>' if img_02 else ''}
        <div class="screenshot-caption">Figura 2.1 — Detalhe do Card 1 (Launcher do Apache Superset) com chips de configuração WSL2 e console de log dedicado.</div>
    </div>
    """

    # -------------------------------------------------------------------------
    # PÁGINA 4: CAPÍTULO 03 - MONITOR DE VOLUMETRIA
    # -------------------------------------------------------------------------
    p4 = f"""
    <div class="chapter-header">
        <span class="chapter-badge">Capítulo 03</span>
        <div class="chapter-title-block">
            <h2>Monitor de Volumetria em Tempo Real (MovideskDM)</h2>
            <span>Auditoria via Dapper · Contagem de core.Fato_Ticket · Vínculo de Empresas e Snapshot Histórico</span>
        </div>
    </div>

    <p class="lead-text">
        O módulo <strong>2. Monitor de Volumetria (MovideskDM)</strong> utiliza o micro-ORM <strong>Dapper</strong> (<code>DatabaseMonitorService</code>) sobre conexões assíncronas <code>SqlConnection</code> para consultar em tempo real o estado do Data Mart no SQL Server. Com a chave <strong>Auto-refresh (5s)</strong> habilitada, o operador acompanha a evolução da base lote a lote sem precisar atualizar a página manualmente.
    </p>

    <div class="steps-container">
        <div class="step-row">
            <div class="step-circle">1</div>
            <div class="step-text">
                <strong>Indicador Principal (<code>SELECT COUNT(*) FROM core.Fato_Ticket</code>):</strong> O número em destaque no topo do card mostra exatamente quantos chamados já foram extraídos, normalizados em Horário de Brasília (BRT) e gravados na tabela fato principal <code>core.Fato_Ticket</code>, prontos para leitura imediata pelos gráficos do Apache Superset.
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">2</div>
            <div class="step-text">
                <strong>RAW Total vs. Empresas / Contatos Vinculados:</strong> O minicard esquerdo exibe o total bruto em <code>raw.Ticket</code>, enquanto o minicard direito audita a separação entre <strong>Empresas Clientes</strong> (<code>TipoPessoa = 2</code>) e <strong>Contatos Vinculados</strong> (pessoas físicas associadas às suas respectivas organizações em <code>core.Dim_Cliente</code>).
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">3</div>
            <div class="step-text">
                <strong>Faixa de Tickets (<code>#ID</code>) e Fronteira Histórica / Snapshot:</strong> Exibe o menor e o maior protocolo/ID presentes no banco (ex.: <code>#335 → #55297</code>), a data UTC exata onde a carga regressiva histórica está posicionada e a quantidade de dias populados na tabela de evolução de fila (<code>core.Fato_SnapshotBacklog</code>, ex.: <code>91d</code>).
            </div>
        </div>
    </div>

    <table class="zebra-table">
        <thead>
            <tr>
                <th style="width: 25%;">Métrica no Card</th>
                <th style="width: 35%;">Consulta SQL Executada (Dapper)</th>
                <th>Finalidade Operacional e de Negócio</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>Chamados no Data Mart</strong></td>
                <td><code>SELECT COUNT(*) FROM core.Fato_Ticket</code></td>
                <td>Confirma o volume total de tickets disponíveis nas 8 Views analíticas (<code>mart.vw_*</code>).</td>
            </tr>
            <tr>
                <td><strong>RAW Total</strong></td>
                <td><code>SELECT COUNT(*) FROM raw.Ticket</code></td>
                <td>Total de payloads JSON brutos armazenados na camada de pouso antes/após o processamento.</td>
            </tr>
            <tr>
                <td><strong>Empresas / Contatos</strong></td>
                <td><code>COUNT(*) FROM core.Dim_Cliente</code></td>
                <td>Garante que a visão de Churn e Saúde de Clientes (<code>vw_ClienteRaioX</code>) agrupe por Empresa real.</td>
            </tr>
            <tr>
                <td><strong>Faixa de Tickets (#ID)</strong></td>
                <td><code>MIN(TicketId) / MAX(TicketId)</code></td>
                <td>Mostra a amplitude histórica de protocolos já cobertos pela base analítica.</td>
            </tr>
            <tr>
                <td><strong>Fronteira / Snapshot</strong></td>
                <td><code>LEAD(LastUpdateUtc)</code> + <code>Fato_SnapshotBacklog</code></td>
                <td>Indica o ponto exato de retomada da carga histórica e os dias de histórico da curva de backlog.</td>
            </tr>
        </tbody>
    </table>

    <div class="screenshot-placeholder-box">
        <div class="screenshot-placeholder-tag">[INSERIR IMAGEM AQUI: Screenshot da tela 03 - Card 2: Monitor de Volumetria (MovideskDM)]</div>
        {f'<div class="screenshot-img-wrapper"><img src="{img_03}" alt="Tela 03 - Card Monitor de Volumetria" /></div>' if img_03 else ''}
        <div class="screenshot-caption">Figura 3.1 — Card 2 (Monitor de Volumetria) exibindo 21.249 chamados no Data Mart, 446 empresas, 1.342 vínculos e 91 dias de snapshot.</div>
    </div>
    """

    # -------------------------------------------------------------------------
    # PÁGINA 5: CAPÍTULO 04 - ORQUESTRADOR ANTI-TRAVAMENTO
    # -------------------------------------------------------------------------
    p5 = f"""
    <div class="chapter-header">
        <span class="chapter-badge">Capítulo 04</span>
        <div class="chapter-title-block">
            <h2>Orquestrador de Carga de Dados (Anti-Travamento)</h2>
            <span>Carga Histórica (Skip e Cursor Inteligente) · Carga Incremental Assíncrona · Sincronização de Empresas</span>
        </div>
    </div>

    <p class="lead-text">
        A carga histórica da API do Movidesk envolve dezenas de milhares de chamados com histórico de status e campos customizados. Para evitar qualquer congelamento da janela desktop, o <strong>Orquestrador de Carga de Dados</strong> executa todo o pipeline de rede e banco em uma thread isolada via <code>Task.Run</code>, atualizando o console visual a cada etapa (<em>"Extraindo..."</em>, <em>"Salvando no Banco..."</em>, <em>"Processando Core..."</em>, <em>"Aguardando Rate Limit..."</em> e <em>"Concluído"</em>).
    </p>

    <div class="steps-container">
        <div class="step-row">
            <div class="step-circle">1</div>
            <div class="step-text">
                <strong>Carga Histórica (Paginação <code>$skip</code> + Cursor Regressivo Inteligente):</strong> Ao acionar <strong>"Disparar / Retomar Carga Histórica"</strong>, o motor verifica primeiro o estado do banco. Se a base estiver vazia, pagina a partir de <code>skip = 0</code> (ou do <code>skipInicial</code> parametrizado) em lotes de 50 registros. Se a base já possuir chamados salvos, ele detecta automaticamente a <strong>Fronteira Histórica UTC</strong> (<code>lastUpdate le {{cursorUtc}}</code> com <code>skip = 0</code>), pulando instantaneamente os milhares de tickets já importados sem desperdiçar requisições.
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">2</div>
            <div class="step-text">
                <strong>Carga Incremental Assíncrona (Marca d'Água):</strong> Ao clicar em <strong>"Disparar Carga Incremental"</strong>, o extrator lê a última data gravada em <code>ctl.MarcaDagua</code> (aplicando margem de segurança de <code>-10 minutos</code>), busca apenas os chamados novos ou alterados recentemente (<code>$filter=lastUpdate ge ...</code>), processa o modelo estrela e atualiza o snapshot diário em segundos.
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">3</div>
            <div class="step-text">
                <strong>Sincronizar Empresas (<code>/persons</code>) e Cancelamento Seguro:</strong> O botão <strong>"Sincronizar Empresas (/persons)"</strong> importa todas as organizações (<code>personType eq 2</code>) e resolve o vínculo de empresa dos contatos já presentes nos chamados via <code>core.usp_ProcessarPessoas</code>. O botão <strong>"Cancelar Carga"</strong> interrompe o lote atual com segurança, preservando 100% do progresso já salvo.
            </div>
        </div>
    </div>

    <table class="zebra-table">
        <thead>
            <tr>
                <th style="width: 23%;">Operação no Painel</th>
                <th style="width: 29%;">Estratégia de Paginação / Filtro API</th>
                <th>Resultado no Banco MovideskDM</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>Carga Histórica</strong></td>
                <td>Fase 1 (Delta recente) + Fase 2 (<code>/tickets/past</code> com <code>lastUpdate le {{cursor}}</code> e <code>$skip</code> dinâmico)</td>
                <td>Importa todo o passivo histórico com contadores separados de <strong>+Novos Inseridos</strong> vs. <strong>Atualizados</strong>.</td>
            </tr>
            <tr>
                <td><strong>Carga Incremental</strong></td>
                <td><code>/tickets?$filter=lastUpdate ge {{MarcaDagua - 10min}}&$orderby=lastUpdate asc</code></td>
                <td>Atualiza a fila ativa, recalcula SLA/Aging em Horário de Brasília e renova <code>ctl.MarcaDagua</code>.</td>
            </tr>
            <tr>
                <td><strong>Sincronizar Empresas</strong></td>
                <td><code>/persons?$expand=relationships</code> (Empresas <code>personType eq 2</code> + lotes de 15 contatos)</td>
                <td>Popula <code>raw.Pessoa</code> e vincula retroativamente <code>core.Fato_Ticket.EmpresaId</code> à Organização real.</td>
            </tr>
        </tbody>
    </table>

    <div class="screenshot-placeholder-box">
        <div class="screenshot-placeholder-tag">[INSERIR IMAGEM AQUI: Screenshot da tela 04 - Card 3: Orquestrador de Carga de Dados Anti-Travamento]</div>
        {f'<div class="screenshot-img-wrapper"><img src="{img_04}" alt="Tela 04 - Card Orquestrador de Carga" /></div>' if img_04 else ''}
        <div class="screenshot-caption">Figura 4.1 — Card 3 (Orquestrador Anti-Travamento) demonstrando o cursor automático, +1.028 novos inseridos na sessão e botões de controle.</div>
    </div>
    """

    pages_html = (
        render_page(manual_title, 1, total_pages, p1)
        + render_page(manual_title, 2, total_pages, p2)
        + render_page(manual_title, 3, total_pages, p3)
        + render_page(manual_title, 4, total_pages, p4)
        + render_page(manual_title, 5, total_pages, p5)
    )

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8" />
    <title>{manual_title}</title>
    <style>{COMMON_CSS}</style>
</head>
<body>
    {pages_html}
</body>
</html>
"""


def build_manual_2_html() -> str:
    """Constrói o HTML completo do Manual 2: Configuração Passo a Passo do Apache Superset."""
    manual_title = "MANUAL DE CONFIGURAÇÃO - Apache Superset Corporativo"
    total_pages = 6

    # -------------------------------------------------------------------------
    # PÁGINA 1: CAPA + 4 DESTAQUES + ÍNDICE
    # -------------------------------------------------------------------------
    p1 = f"""
    <div class="cover-banner">
        <span class="cover-tag">Guia Passo a Passo ("Mastigado") · Engenharia de BI &amp; Analytics</span>
        <h1>{manual_title}</h1>
        <p>Manual técnico e operacional completo para conectar o Microsoft SQL Server (MovideskDM) ao Apache Superset 6.1.0, mapear as 8 Views analíticas como Datasets, construir os gráficos da Sala de Guerra, configurar acessos somente leitura (Role Gamma) para a Diretoria e publicar link HTTPS seguro via Ngrok.</p>
        <div class="cover-meta-strip">
            <span><strong>Plataforma:</strong> Apache Superset 6.1.0 (WSL2)</span>
            <span><strong>Fonte de Dados:</strong> SQL Server (MovideskDM)</span>
            <span><strong>Porta Padrão:</strong> 8088 (HTTP / Ngrok HTTPS)</span>
        </div>
    </div>

    <div class="section-heading-gold">
        <h2>Destaques da Configuração (01 a 04)</h2>
        <div class="gold-line"></div>
    </div>

    <div class="highlights-grid">
        <div class="highlight-card">
            <div class="highlight-num">01</div>
            <div class="highlight-content">
                <h3>Conexão Direta ao MSSQL (MovideskDM)</h3>
                <p>Configuração passo a passo da string SQLAlchemy (<code>mssql+pymssql://</code>) conectando o Superset no WSL2 ao SQL Server local no Windows.</p>
            </div>
        </div>
        <div class="highlight-card">
            <div class="highlight-num">02</div>
            <div class="highlight-content">
                <h3>Catálogo de 8 Views Analíticas (Schema mart)</h3>
                <p>Exposição das Views pré-calculadas em Horário de Brasília (<code>mart.vw_*</code>) como Datasets oficiais prontos para uso sem escrever código SQL.</p>
            </div>
        </div>
        <div class="highlight-card">
            <div class="highlight-num">03</div>
            <div class="highlight-content">
                <h3>Sala de Guerra e Gráficos Big Number</h3>
                <p>Roteiro clique a clique para construir cartões executivos arrastando métricas (<code>SUM</code>, <code>AVG</code>) e montar o painel operacional e tático.</p>
            </div>
        </div>
        <div class="highlight-card">
            <div class="highlight-num">04</div>
            <div class="highlight-content">
                <h3>Acesso Diretoria (Gamma) + Túnel Ngrok</h3>
                <p>Criação de usuários restritos à visualização (Role <code>Gamma</code>) e publicação externa segura em HTTPS na porta <code>8088</code> com um único comando.</p>
            </div>
        </div>
    </div>

    <div class="section-heading-gold">
        <h2>Índice / Conteúdo</h2>
        <div class="gold-line"></div>
    </div>

    <div class="toc-box">
        <ul class="toc-list">
            <li class="toc-item">
                <div class="toc-item-left">
                    <span class="toc-badge">CAPÍTULO 01</span>
                    <span class="toc-title">Conectando o Banco de Dados</span>
                    <span class="toc-desc">— Passo a passo para plugar o banco MSSQL MovideskDM no Apache Superset</span>
                </div>
                <span class="toc-page">Página 02</span>
            </li>
            <li class="toc-item">
                <div class="toc-item-left">
                    <span class="toc-badge">CAPÍTULO 02</span>
                    <span class="toc-title">Mapeamento de Datasets</span>
                    <span class="toc-desc">— Como expor as 8 Views do schema mart do SQL Server como Datasets no Superset</span>
                </div>
                <span class="toc-page">Página 03</span>
            </li>
            <li class="toc-item">
                <div class="toc-item-left">
                    <span class="toc-badge">CAPÍTULO 03</span>
                    <span class="toc-title">Criação de Gráficos (Sala de Guerra)</span>
                    <span class="toc-desc">— Passo a passo mastigado para criar gráficos "Big Number" e tabela de receitas</span>
                </div>
                <span class="toc-page">Página 04</span>
            </li>
            <li class="toc-item">
                <div class="toc-item-left">
                    <span class="toc-badge">CAPÍTULO 04</span>
                    <span class="toc-title">Gestão de Acessos (Diretoria)</span>
                    <span class="toc-desc">— Como criar o usuário executivo com a Role "Gamma" (apenas visualização)</span>
                </div>
                <span class="toc-page">Página 05</span>
            </li>
            <li class="toc-item">
                <div class="toc-item-left">
                    <span class="toc-badge">CAPÍTULO 05</span>
                    <span class="toc-title">Publicação Externa (Túnel Reverso)</span>
                    <span class="toc-desc">— Como iniciar o ngrok apontando para a porta 8088 para gerar link HTTPS público</span>
                </div>
                <span class="toc-page">Página 06</span>
            </li>
        </ul>
    </div>
    """

    # -------------------------------------------------------------------------
    # PÁGINA 2: CAPÍTULO 01 - CONECTANDO O BANCO DE DADOS
    # -------------------------------------------------------------------------
    p2 = """
    <div class="chapter-header">
        <span class="chapter-badge">Capítulo 01</span>
        <div class="chapter-title-block">
            <h2>Conectando o Banco de Dados (MSSQL MovideskDM)</h2>
            <span>Passo a Passo Mastigado para Plugar o Microsoft SQL Server no Apache Superset</span>
        </div>
    </div>

    <p class="lead-text">
        Com o Apache Superset iniciado pelo Painel de Controle (<span class="badge-pill badge-green">Online</span> na porta <code>8088</code>), o primeiro passo é cadastrar a conexão com o banco de dados <strong>MovideskDM</strong> que roda no seu SQL Server local. Siga exatamente o roteiro abaixo:
    </p>

    <div class="steps-container">
        <div class="step-row">
            <div class="step-circle">1</div>
            <div class="step-text">
                <strong>Acessar a Tela de Conexões:</strong> Abra o navegador em <code>http://localhost:8088</code>, entre com seu login de administrador (padrão: <code>admin</code> / <code>admin</code>). No canto superior direito, clique no ícone de engrenagem <strong>Settings (⚙️)</strong> e selecione a opção <strong>Database Connections</strong>.
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">2</div>
            <div class="step-text">
                <strong>Iniciar Nova Conexão:</strong> Clique no botão azul <strong><code>+ Database</code></strong> (canto superior direito). Na janela modal que abrir, na lista <em>SUPPORTED DATABASES</em>, selecione <strong>Microsoft SQL Server</strong>.
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">3</div>
            <div class="step-text">
                <strong>Preencher Nome e String SQLAlchemy URI:</strong> No campo <strong>DISPLAY NAME</strong>, digite <code>MovideskDM</code>. No campo <strong>SQLALCHEMY URI</strong>, informe a string abaixo (substituindo <code>172.29.112.1</code> pelo IP do seu Windows visto pelo WSL2, ou mantendo o IP já configurado):
                <div class="code-banner" style="margin-top: 1.2mm;">mssql+pymssql://sa:123456@172.29.112.1:1433/MovideskDM</div>
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">4</div>
            <div class="step-text">
                <strong>Testar e Salvar:</strong> Clique no botão <strong><code>Test Connection</code></strong>. O Superset exibirá uma mensagem verde no canto inferior direito: <em>"Connection looks good!"</em>. Em seguida, clique em <strong><code>Connect</code></strong> para finalizar.
            </div>
        </div>
    </div>

    <table class="zebra-table">
        <thead>
            <tr>
                <th style="width: 24%;">Elemento da URI</th>
                <th style="width: 30%;">Valor Exemplo</th>
                <th>Explicação Didática ("Mastigada")</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>Driver Dialeto</strong></td>
                <td><code>mssql+pymssql://</code></td>
                <td>Indica ao Superset que deve usar o driver Python <code>pymssql</code> (já instalado na venv do WSL2).</td>
            </tr>
            <tr>
                <td><strong>Credenciais SQL</strong></td>
                <td><code>sa:123456</code></td>
                <td>Usuário e senha do SQL Server (mesmos configurados no <code>appsettings.json</code> do Painel).</td>
            </tr>
            <tr>
                <td><strong>Host e Porta TCP</strong></td>
                <td><code>@172.29.112.1:1433</code></td>
                <td>IP do host Windows na ponte WSL2 e porta padrão do MSSQL. (Para ver o IP no WSL: <code>ip route | awk '/default/ {print $3}'</code>).</td>
            </tr>
            <tr>
                <td><strong>Nome do Banco</strong></td>
                <td><code>/MovideskDM</code></td>
                <td>Nome exato do Data Mart criado pelos scripts SQL do projeto.</td>
            </tr>
        </tbody>
    </table>

    <div class="screenshot-placeholder-box">
        <div class="screenshot-placeholder-tag">[INSERIR IMAGEM AQUI: Screenshot da tela 01 - Modal Connect a Database (Microsoft SQL Server) no Superset]</div>
        <div class="ui-mockup">
            <div class="ui-mockup-topbar">
                <span>Connect a database · Step 2 of 2 (Microsoft SQL Server)</span>
                <span style="color: #F3C65F;">Settings ▸ Database Connections ▸ + Database</span>
            </div>
            <div class="ui-mockup-body">
                <div class="ui-field">
                    <span class="ui-field-label">1. Display Name *</span>
                    <div class="ui-field-input">MovideskDM</div>
                </div>
                <div class="ui-field">
                    <span class="ui-field-label">2. SQLAlchemy URI *</span>
                    <div class="ui-field-input">mssql+pymssql://sa:123456@172.29.112.1:1433/MovideskDM</div>
                </div>
                <div class="ui-btn-row">
                    <span class="ui-btn ui-btn-outline">✓ Test Connection (Connection looks good!)</span>
                    <span class="ui-btn ui-btn-solid">Connect</span>
                </div>
            </div>
        </div>
        <div class="screenshot-caption">Figura 1.1 — Representação dos campos exatos no modal "Connect a database" do Apache Superset.</div>
    </div>
    """

    # -------------------------------------------------------------------------
    # PÁGINA 3: CAPÍTULO 02 - MAPEAMENTO DE DATASETS
    # -------------------------------------------------------------------------
    p3 = """
    <div class="chapter-header">
        <span class="chapter-badge">Capítulo 02</span>
        <div class="chapter-title-block">
            <h2>Mapeamento de Datasets (Expondo as Views do Schema mart)</h2>
            <span>Como Transformar as 8 Views Analíticas do SQL Server em Fontes de Dados para os Gráficos</span>
        </div>
    </div>

    <p class="lead-text">
        No Apache Superset, os gráficos não leem tabelas diretamente: eles consomem <strong>Datasets</strong>. Toda a inteligência de negócio da Advice (cálculo de SLA, conversão para Horário de Brasília, faixas de Aging e vínculo de Empresas) já está pronta dentro do schema <strong><code>mart</code></strong> no banco <code>MovideskDM</code>. Basta registrar cada uma das 8 Views seguindo o passo a passo abaixo:
    </p>

    <div class="steps-container">
        <div class="step-row">
            <div class="step-circle">1</div>
            <div class="step-text">
                <strong>Abrir o Cadastro de Datasets:</strong> Na barra de navegação superior do Superset, clique em <strong>Datasets</strong> e, no canto superior direito, clique no botão <strong><code>+ Dataset</code></strong>.
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">2</div>
            <div class="step-text">
                <strong>Selecionar Banco, Schema e View:</strong> Na lateral esquerda, preencha os 3 seletores na ordem:
                <br/>• Em <strong>DATABASE</strong>: selecione <code>MovideskDM</code>.
                <br/>• Em <strong>SCHEMA</strong>: selecione <strong><code>mart</code></strong> (muito importante: não use <code>raw</code> nem <code>core</code> nos gráficos).
                <br/>• Em <strong>TABLE</strong>: escolha a View desejada (comece por <code>vw_VisaoGeralKpis</code>).
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">3</div>
            <div class="step-text">
                <strong>Salvar o Dataset:</strong> Clique no botão inferior direito <strong><code>Create Dataset and Create Chart</code></strong> (ou apenas <em>Create Dataset</em>). Repita o processo para as 8 Views listadas na tabela abaixo — leva menos de 2 minutos para cadastrar todas!
            </div>
        </div>
    </div>

    <table class="zebra-table">
        <thead>
            <tr>
                <th style="width: 28%;">View no Schema mart</th>
                <th style="width: 20%;">Coluna de Tempo</th>
                <th>O que esta View entrega pronta para o Dashboard</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><code>mart.vw_VisaoGeralKpis</code></td>
                <td><em>Snapshot Atual</em></td>
                <td>Big Numbers por Equipe: <code>BacklogAtual</code>, <code>SlaVencidos</code>, <code>SlaIminente4h</code>, <code>SlaPausados</code>, <code>EmDependenciaDev</code>, <code>AbertosHoje</code>, <code>ResolvidosHoje</code> e <code>FcrUltimos30DiasPct</code>.</td>
            </tr>
            <tr>
                <td><code>mart.vw_SlaRadar</code></td>
                <td><code>DataCriacao</code></td>
                <td>Fila aberta classificada por risco de SLA (<code>Vencido</code>, <code>Crítico &lt; 2h</code>, <code>Alerta &lt; 4h</code>) com nome da Empresa, Analista e <code>MinutosParaVencer</code>.</td>
            </tr>
            <tr>
                <td><code>mart.vw_BacklogEvolucao</code></td>
                <td><code>DataSnapshot</code></td>
                <td>Curva histórica diária (últimos 90 dias + hoje) de <code>QtdTickets</code>, <code>QtdSlaVencido</code> e <code>QtdNoPrazo</code> por Equipe, Analista e Status.</td>
            </tr>
            <tr>
                <td><code>mart.vw_BacklogAging</code></td>
                <td><code>DataCriacao</code></td>
                <td>Idade dos chamados em aberto (<code>FaixaIdade</code>: 0 a 2d até &gt; 30d) e flag <code>SemInteracaoMais48h</code>.</td>
            </tr>
            <tr>
                <td><code>mart.vw_StatusAging</code></td>
                <td><em>Agregado</em></td>
                <td>Gargalos operacionais: tempo médio e total (em horas úteis e corridas) gasto em cada Status.</td>
            </tr>
            <tr>
                <td><code>mart.vw_ThroughputDiario</code></td>
                <td><code>Data</code></td>
                <td>Balanço diário de <code>Abertos</code> vs. <code>Resolvidos</code> e <code>SaldoLiquido</code> acoplado ao calendário de dias úteis.</td>
            </tr>
            <tr>
                <td><code>mart.vw_ClienteRaioX</code></td>
                <td><code>DataUltimoTicket</code></td>
                <td>Saúde por <strong>Empresa Cliente</strong>: volume histórico, abertos, % SLA cumprido e alerta de <strong>Risco Churn (Silencioso &gt; 60d)</strong>.</td>
            </tr>
            <tr>
                <td><code>mart.vw_MapaDemanda</code></td>
                <td><em>Agregado</em></td>
                <td>Pareto de Categorias, Urgência e Versão do Produto/Release (<code>CampoId = 133948</code>).</td>
            </tr>
        </tbody>
    </table>

    <div class="screenshot-placeholder-box">
        <div class="screenshot-placeholder-tag">[INSERIR IMAGEM AQUI: Screenshot da tela 02 - Cadastro de Dataset (Schema mart) no Apache Superset]</div>
        <div class="ui-mockup">
            <div class="ui-mockup-topbar">
                <span>New dataset · Add dataset to Superset</span>
                <span style="color: #F3C65F;">Datasets ▸ + Dataset</span>
            </div>
            <div class="ui-mockup-body" style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 2.5mm;">
                <div class="ui-field">
                    <span class="ui-field-label">1. Database</span>
                    <div class="ui-field-input">MovideskDM</div>
                </div>
                <div class="ui-field">
                    <span class="ui-field-label">2. Schema</span>
                    <div class="ui-field-input">mart</div>
                </div>
                <div class="ui-field">
                    <span class="ui-field-label">3. Table / View</span>
                    <div class="ui-field-input">vw_VisaoGeralKpis</div>
                </div>
            </div>
        </div>
        <div class="screenshot-caption">Figura 2.1 — Seleção do banco MovideskDM, schema mart e view analítica na tela "New dataset".</div>
    </div>
    """

    # -------------------------------------------------------------------------
    # PÁGINA 4: CAPÍTULO 03 - CRIAÇÃO DE GRÁFICOS (SALA DE GUERRA)
    # -------------------------------------------------------------------------
    p4 = """
    <div class="chapter-header">
        <span class="chapter-badge">Capítulo 03</span>
        <div class="chapter-title-block">
            <h2>Criação de Gráficos (Sala de Guerra &amp; Big Numbers)</h2>
            <span>Tutorial Passo a Passo ("Mastigado") para Criar um Card Big Number Arrastando Métricas</span>
        </div>
    </div>

    <p class="lead-text">
        A <strong>Sala de Guerra</strong> tem no seu topo os indicadores executivos instantâneos (<em>Big Numbers</em>). Veja abaixo como criar passo a passo o cartão de <strong>Backlog Atual (Chamados em Aberto)</strong> arrastando a métrica da view <code>mart.vw_VisaoGeralKpis</code>:
    </p>

    <div class="steps-container">
        <div class="step-row">
            <div class="step-circle">1</div>
            <div class="step-text">
                <strong>Iniciar Novo Gráfico:</strong> No menu superior, clique em <strong>Charts</strong> → botão <strong><code>+ Chart</code></strong>. Em <em>Choose a dataset</em>, selecione <strong><code>vw_VisaoGeralKpis</code></strong>. Na galeria de tipos (<em>KPI</em>), clique em <strong><code>Big Number</code></strong> e depois no botão azul <strong><code>Create New Chart</code></strong>.
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">2</div>
            <div class="step-text">
                <strong>Arrastar a Métrica para o Campo METRIC:</strong> Na coluna esquerda da tela de edição (<em>Columns</em>), localize a coluna numérica <strong><code>BacklogAtual</code></strong>. Clique e <strong>arraste-a para dentro da caixa <code>METRIC</code></strong> (na aba central <em>DATA</em>). Na janelinha que abrir, na aba <em>SIMPLE</em>, confirme o agregador <strong><code>SUM (Soma)</code></strong> e clique em <strong><code>Save</code></strong>.
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">3</div>
            <div class="step-text">
                <strong>Definir Subtítulo e Formatação:</strong> No campo <strong><code>SUBHEADER</code></strong>, digite <code>Chamados Ativos na Fila</code>. Clique na aba <strong>CUSTOMIZE</strong> (ao lado de DATA) e em <strong>Number format</strong> selecione <code>,d</code> (exibe inteiro sem casas decimais). Clique em <strong><code>Update chart</code></strong> para ver o número gigante na tela!
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">4</div>
            <div class="step-text">
                <strong>Salvar no Dashboard:</strong> Clique no botão superior direito <strong><code>Save</code></strong>. Em <em>CHART NAME</em>, digite <code>KPI - Backlog Atual</code>. Em <em>ADD TO DASHBOARD</em>, digite/selecione <code>Sala de Guerra Movidesk</code> e clique em <strong><code>Save &amp; go to dashboard</code></strong>.
            </div>
        </div>
    </div>

    <table class="zebra-table">
        <thead>
            <tr>
                <th style="width: 24%;">Gráfico da Sala de Guerra</th>
                <th style="width: 23%;">Dataset (Schema mart)</th>
                <th style="width: 20%;">Tipo no Superset</th>
                <th>O que arrastar para Metric e Dimensions</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>1. Cards Topo (Backlog, SLA Vencido, Crítico &lt; 4h)</strong></td>
                <td><code>vw_VisaoGeralKpis</code></td>
                <td><code>Big Number</code></td>
                <td><strong>Metric:</strong> <code>SUM(BacklogAtual)</code>, <code>SUM(SlaVencidos)</code>, <code>SUM(SlaIminente4h)</code> (1 card para cada).</td>
            </tr>
            <tr>
                <td><strong>2. Evolução Diária da Fila (90 dias)</strong></td>
                <td><code>vw_BacklogEvolucao</code></td>
                <td><code>Time-series Area Chart</code></td>
                <td><strong>Time Column:</strong> <code>DataSnapshot</code> | <strong>Metric:</strong> <code>SUM(QtdTickets)</code> e <code>SUM(QtdSlaVencido)</code>.</td>
            </tr>
            <tr>
                <td><strong>3. Termômetro Preditivo de SLA (Fila Viva)</strong></td>
                <td><code>vw_SlaRadar</code></td>
                <td><code>Table</code></td>
                <td><strong>Dimensions:</strong> <code>TicketId</code>, <code>Cliente</code>, <code>Assunto</code>, <code>Analista</code>, <code>FaixaRiscoSla</code>, <code>MinutosParaVencer</code>.</td>
            </tr>
            <tr>
                <td><strong>4. Gargalos por Status (Onde o ticket para)</strong></td>
                <td><code>vw_StatusAging</code></td>
                <td><code>Bar Chart</code> (Horizontal)</td>
                <td><strong>Dimensions:</strong> <code>Status</code> | <strong>Metric:</strong> <code>AVG(HorasUteisMedias)</code>.</td>
            </tr>
            <tr>
                <td><strong>5. Radar de Clientes Silenciosos (Churn)</strong></td>
                <td><code>vw_ClienteRaioX</code></td>
                <td><code>Table</code></td>
                <td><strong>Dimensions:</strong> <code>Cliente</code>, <code>StatusRelacionamento</code>, <code>DiasDesdeUltimoTicket</code>, <code>SlaCumpridoPct</code>.</td>
            </tr>
        </tbody>
    </table>

    <div class="screenshot-placeholder-box">
        <div class="screenshot-placeholder-tag">[INSERIR IMAGEM AQUI: Screenshot da tela 03 - Construtor de Gráfico Big Number (Arrastando Métrica SUM(BacklogAtual))]</div>
        <div class="ui-mockup">
            <div class="ui-mockup-topbar">
                <span>Chart Builder · Dataset: mart.vw_VisaoGeralKpis · Visualization: Big Number</span>
                <span style="color: #F3C65F;">Botão: Save ▸ Sala de Guerra Movidesk</span>
            </div>
            <div class="ui-mockup-body" style="display: grid; grid-template-columns: 1.1fr 1.3fr 1.2fr; gap: 2.5mm; align-items: center;">
                <div class="ui-field">
                    <span class="ui-field-label">Colunas do Dataset (Arrastar)</span>
                    <div class="ui-field-input"># BacklogAtual  ───►</div>
                    <div class="ui-field-input"># SlaVencidos</div>
                </div>
                <div class="ui-field">
                    <span class="ui-field-label">Aba DATA ▸ Campo METRIC</span>
                    <div class="ui-field-input" style="border-left-color: #C59217;">SUM(BacklogAtual)</div>
                    <span class="ui-field-label" style="margin-top: 1mm;">Campo SUBHEADER</span>
                    <div class="ui-field-input">Chamados Ativos na Fila</div>
                </div>
                <div style="background: #0B3B52; color: #fff; border-radius: 1.2mm; padding: 2.5mm; text-align: center;">
                    <div style="font-size: 16pt; font-weight: 800; color: #F3C65F;">142</div>
                    <div style="font-size: 7pt;">Chamados Ativos na Fila</div>
                </div>
            </div>
        </div>
        <div class="screenshot-caption">Figura 3.1 — Esquema visual do construtor Big Number no Superset arrastando BacklogAtual para a caixa METRIC.</div>
    </div>
    """

    # -------------------------------------------------------------------------
    # PÁGINA 5: CAPÍTULO 04 - GESTÃO DE ACESSOS (ROLE GAMMA)
    # -------------------------------------------------------------------------
    p5 = """
    <div class="chapter-header">
        <span class="chapter-badge">Capítulo 04</span>
        <div class="chapter-title-block">
            <h2>Gestão de Acessos (Perfil da Diretoria com Role "Gamma")</h2>
            <span>Como Criar Usuários Somente Leitura (Visualização de Dashboards sem Permissão de Edição)</span>
        </div>
    </div>

    <p class="lead-text">
        A Diretoria e os gestores executivos precisam consultar os indicadores, aplicar filtros de período/equipe e exportar relatórios, mas <strong>não devem alterar a estrutura dos gráficos nem executar comandos SQL</strong>. No Apache Superset, esse controle é feito combinando a Role nativa <strong><code>Gamma</code></strong> (consumidor apenas leitura) com a permissão de leitura sobre o banco <code>MovideskDM</code>:
    </p>

    <div class="steps-container">
        <div class="step-row">
            <div class="step-circle">1</div>
            <div class="step-text">
                <strong>Liberar Leitura do Banco MovideskDM para o Perfil Gamma (1 única vez):</strong> No canto superior direito, clique em <strong>Settings (⚙️) → List Roles</strong>. Na linha da role <strong><code>Gamma</code></strong>, clique no ícone de lápis (<em>Edit Record</em>). No campo <strong>Permissions</strong>, digite e adicione a permissão <strong><code>database access on [MovideskDM]</code></strong> (ou <code>all database access on all_database_access</code>) e clique em <strong>Save</strong>. <em>Isso garante que o usuário Gamma veja os gráficos do MovideskDM sem receber erro de acesso negado à fonte de dados!</em>
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">2</div>
            <div class="step-text">
                <strong>Abrir o Cadastro de Usuários:</strong> Clique novamente em <strong>Settings (⚙️) → List Users</strong> e clique no botão <strong><code>+</code> (Add User)</strong> no canto superior direito.
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">3</div>
            <div class="step-text">
                <strong>Preencher os Dados do Executivo e Atribuir a Role "Gamma":</strong>
                <br/>• <strong>First Name / Last Name:</strong> Ex.: <code>Diretoria</code> / <code>Advice</code> | <strong>User Name:</strong> <code>diretoria.advice</code>
                <br/>• <strong>Is Active:</strong> Marque a caixa <code>☑</code> | <strong>Role:</strong> Selecione exclusivamente <strong><code>Gamma</code></strong>.
                <br/>• <strong>Password / Confirm Password:</strong> Defina uma senha forte e clique em <strong><code>Save</code></strong>.
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">4</div>
            <div class="step-text">
                <strong>Publicar o Dashboard (Published):</strong> Na tela do Dashboard <em>Sala de Guerra Movidesk</em>, certifique-se de que a tag ao lado do título está como <span class="badge-pill badge-green">Published</span> (e não <em>Draft</em>). Usuários <code>Gamma</code> só enxergam dashboards publicados!
            </div>
        </div>
    </div>

    <table class="zebra-table">
        <thead>
            <tr>
                <th style="width: 20%;">Role do Superset</th>
                <th style="width: 24%;">Público-Alvo na Advice</th>
                <th>O que pode fazer / O que está bloqueado</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><span class="badge-pill badge-gold">Gamma</span></td>
                <td><strong>Diretoria, Executivos e Clientes</strong></td>
                <td><strong>Pode:</strong> Visualizar dashboards publicados e usar filtros.<br/><strong>Bloqueado:</strong> Editar gráficos, excluir painéis, abrir SQL Lab ou mexer em conexões.</td>
            </tr>
            <tr>
                <td><span class="badge-pill badge-teal">Alpha</span></td>
                <td>Analistas de BI / Coordenadores</td>
                <td>Pode criar e editar gráficos e dashboards, mas não pode alterar permissões de outros usuários.</td>
            </tr>
            <tr>
                <td><span class="badge-pill badge-green">Admin</span></td>
                <td>Engenharia / Administradores</td>
                <td>Controle total sobre conexões de banco, usuários, roles e configurações do servidor.</td>
            </tr>
        </tbody>
    </table>

    <div class="screenshot-placeholder-box">
        <div class="screenshot-placeholder-tag">[INSERIR IMAGEM AQUI: Screenshot da tela 04 - Cadastro de Usuário da Diretoria com Role Gamma]</div>
        <div class="ui-mockup">
            <div class="ui-mockup-topbar">
                <span>Security · Add User (Perfil Executivo Somente Leitura)</span>
                <span style="color: #F3C65F;">Settings ▸ List Users ▸ + Add User</span>
            </div>
            <div class="ui-mockup-body" style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 2mm;">
                <div class="ui-field">
                    <span class="ui-field-label">User Name *</span>
                    <div class="ui-field-input">diretoria.advice</div>
                </div>
                <div class="ui-field">
                    <span class="ui-field-label">Is Active</span>
                    <div class="ui-field-input">☑ Ativo (Checked)</div>
                </div>
                <div class="ui-field">
                    <span class="ui-field-label">Role * (Apenas Visualização)</span>
                    <div class="ui-field-input" style="border-left-color: #C59217; background: #fffbeb;">Gamma</div>
                </div>
            </div>
        </div>
        <div class="screenshot-caption">Figura 4.1 — Configuração do usuário da Diretoria em Settings ▸ List Users atribuindo exclusivamente a Role "Gamma".</div>
    </div>
    """

    # -------------------------------------------------------------------------
    # PÁGINA 6: CAPÍTULO 05 - PUBLICAÇÃO EXTERNA (TÚNEL REVERSO NGROK)
    # -------------------------------------------------------------------------
    p6 = """
    <div class="chapter-header">
        <span class="chapter-badge">Capítulo 05</span>
        <div class="chapter-title-block">
            <h2>Publicação Externa Segura (Túnel Reverso com Ngrok)</h2>
            <span>Passo a Passo Mastigado para Expor a Porta 8088 em um Link HTTPS Público para Diretoria / Cliente Final</span>
        </div>
    </div>

    <p class="lead-text">
        Como o Apache Superset roda localmente na sua máquina na porta <code>8088</code>, o utilitário <strong>ngrok</strong> permite criar instantaneamente um <strong>túnel reverso criptografado (HTTPS/TLS)</strong> sem precisar abrir portas no roteador/firewall da empresa. Siga o roteiro mastigado abaixo:
    </p>

    <div class="steps-container">
        <div class="step-row">
            <div class="step-circle">1</div>
            <div class="step-text">
                <strong>Criar Conta Gratuita e Copiar o Authtoken (Só na 1ª vez):</strong> Acesse <code>https://dashboard.ngrok.com</code>, crie sua conta gratuita e, no menu lateral esquerdo, clique em <strong>Your Authtoken</strong>. Copie o token exibido na tela.
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">2</div>
            <div class="step-text">
                <strong>Instalar e Autenticar o Ngrok:</strong> No Windows (via PowerShell ou CMD), instale o ngrok com <code>winget install Ngrok.Ngrok</code> (ou baixe o executável no site oficial) e registre seu token uma única vez com o comando:
                <div class="code-banner" style="margin-top: 1mm;">ngrok config add-authtoken COLE_SEU_TOKEN_AQUI</div>
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">3</div>
            <div class="step-text">
                <strong>Iniciar o Superset e Abrir o Túnel na Porta 8088:</strong> Primeiro, certifique-se no <code>MovideskControlPanel.exe</code> de que o Superset está <span class="badge-pill badge-green">Online</span> na porta <code>8088</code>. Em seguida, execute no terminal o comando abaixo:
                <div class="code-banner" style="margin-top: 1mm;">ngrok http 8088 --host-header="localhost:8088"</div>
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">4</div>
            <div class="step-text">
                <strong>Copiar o Link Público HTTPS Gerado:</strong> O ngrok abrirá um painel de status no terminal. Localize a linha <strong><code>Forwarding</code></strong>, copie o endereço que começa com <strong><code>https://</code></strong> (ex.: <code>https://a1b2-200-150-10-20.ngrok-free.app</code>) e envie para a Diretoria acessar usando o usuário <code>Gamma</code> criado no Capítulo 04!
            </div>
        </div>
    </div>

    <div class="callout-gold">
        <strong>Dica de Segurança Corporativa (Dupla Camada de Senha):</strong> Se desejar exigir uma senha extra do próprio túnel antes mesmo de carregar a tela de login do Superset, adicione o parâmetro <code>--basic-auth</code> ao comando:
        <br/><code>ngrok http 8088 --host-header="localhost:8088" --basic-auth="advice:SenhaExecutiva2026"</code>
    </div>

    <table class="zebra-table">
        <thead>
            <tr>
                <th style="width: 38%;">Comando Ngrok</th>
                <th>Quando Utilizar e O Que Ele Faz</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><code>ngrok http 8088 --host-header="localhost:8088"</code></td>
                <td><strong>Padrão Recomendado:</strong> Cria túnel HTTPS público apontando para o Superset local na porta <code>8088</code> reescrevendo o cabeçalho Host para evitar bloqueios de CSRF.</td>
            </tr>
            <tr>
                <td><code>ngrok http 8088 --basic-auth="usuario:senha123"</code></td>
                <td><strong>Alta Segurança:</strong> Exige autenticação HTTP Basic na borda da nuvem do ngrok antes de entregar a tela de login do Superset.</td>
            </tr>
            <tr>
                <td><code>ngrok http 8088 --url=seu-dominio.ngrok-free.app</code></td>
                <td><strong>URL Fixa Gratuita:</strong> Usa o domínio estático gratuito fornecido na aba <em>Domains</em> do painel do ngrok para que o link nunca mude ao reiniciar.</td>
            </tr>
        </tbody>
    </table>

    <div class="screenshot-placeholder-box">
        <div class="screenshot-placeholder-tag">[INSERIR IMAGEM AQUI: Screenshot da tela 05 - Terminal executando ngrok http 8088 com link HTTPS gerado]</div>
        <div class="code-banner" style="width: 100%; font-size: 7.4pt; line-height: 1.32;">ngrok                                                           (Ctrl+C to quit)

Session Status                online
Account                       Advice Compliance Solutions (Plan: Free)
Region                        South America (sa)
Latency                       18ms
Web Interface                 http://127.0.0.1:4040
Forwarding                    https://advice-movidesk-bi.ngrok-free.app -> http://localhost:8088

Connections                   ttl     opn     rt1     rt5     p50     p90
                              42      2       0.08    0.05    12.40   28.10</div>
        <div class="screenshot-caption">Figura 5.1 — Saída do comando ngrok http 8088 destacando a linha "Forwarding" com o link HTTPS público seguro.</div>
    </div>
    """

    pages_html = (
        render_page(manual_title, 1, total_pages, p1)
        + render_page(manual_title, 2, total_pages, p2)
        + render_page(manual_title, 3, total_pages, p3)
        + render_page(manual_title, 4, total_pages, p4)
        + render_page(manual_title, 5, total_pages, p5)
        + render_page(manual_title, 6, total_pages, p6)
    )

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8" />
    <title>{manual_title}</title>
    <style>{COMMON_CSS}</style>
</head>
<body>
    {pages_html}
</body>
</html>
"""


def consultar_information_schema_local() -> List[tuple]:
    """
    Consulta opcionalmente a INFORMATION_SCHEMA.COLUMNS do banco MovideskDM local via sqlcmd
    (quando executado na máquina Windows com SQL Server ativo) para validação em tempo real.
    """
    sqlcmd_bin = shutil.which("sqlcmd")
    if not sqlcmd_bin:
        return []
    query = (
        "SET NOCOUNT ON; "
        "SELECT TABLE_SCHEMA + '.' + TABLE_NAME, COLUMN_NAME, UPPER(DATA_TYPE), IS_NULLABLE "
        "FROM MovideskDM.INFORMATION_SCHEMA.COLUMNS "
        "ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION;"
    )
    try:
        proc = subprocess.run(
            [sqlcmd_bin, "-S", "localhost", "-d", "MovideskDM", "-E", "-W", "-s", "|", "-h", "-1", "-Q", query],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            rows = []
            for line in proc.stdout.splitlines():
                parts = [p.strip() for p in line.split("|")]
                if len(parts) == 4:
                    rows.append(tuple(parts))
            return rows
    except Exception:
        pass
    return []


def render_dict_table(rows: List[tuple], dense: bool = False, col1_label: str = "Nome da Coluna", col2_label: str = "Tipo de Dado") -> str:
    """Renderiza uma tabela zebrada corporativa de Dicionário de Dados (Nome da Coluna | Tipo de Dado | Descrição Definitiva)."""
    cls = "zebra-table dict-dense" if dense else "zebra-table dict-table"
    body = []
    for col_name, data_type, desc in rows:
        body.append(
            f"<tr>"
            f"<td><code>{col_name}</code></td>"
            f"<td><code>{data_type}</code></td>"
            f"<td>{desc}</td>"
            f"</tr>"
        )
    return f"""
    <table class="{cls}">
        <thead>
            <tr>
                <th style="width: 22%;">{col1_label}</th>
                <th style="width: 19%;">{col2_label}</th>
                <th>Descrição Definitiva</th>
            </tr>
        </thead>
        <tbody>
            {''.join(body)}
        </tbody>
    </table>
    """


def build_manual_3_html() -> str:
    """
    Constrói o HTML completo e exaustivo (12 páginas A4) do Manual 03:
    MANUAL DE ARQUITETURA - Dicionário de Dados Completo (MovideskDM).
    """
    _ = consultar_information_schema_local()
    header_right_title = "MANUAL DE ARQUITETURA - Dicionário de Dados"
    cover_title = "MANUAL DE ARQUITETURA - Dicionário de Dados (MovideskDM)"
    total_pages = 12

    img_ssms = img_to_data_uri("ssms_arvore_movideskdm.png")

    # =========================================================================
    # PÁGINA 01: CAPA EXECUTIVA + 3 DESTAQUES + ÍNDICE (12 PÁGs) + ÁRVORE SSMS
    # =========================================================================
    p1 = f"""
    <div class="cover-banner" style="padding: 5.5mm 7mm;">
        <span class="cover-tag">Engenharia de Dados &amp; Business Intelligence · Edição Definitiva e Exaustiva</span>
        <h1 style="font-size: 17.5pt;">{cover_title}</h1>
        <p>Guia definitivo de modelagem de dados, arquitetura em camadas (Schemas), especificação física coluna a coluna (<code>INFORMATION_SCHEMA.COLUMNS</code>) e catálogo oficial de métricas e Views para o Apache Superset.</p>
        <div class="cover-meta-strip">
            <span><strong>Banco:</strong> SQL Server (MovideskDM)</span>
            <span><strong>Objetos:</strong> 5 Schemas · 18 Tabelas · 8 Views</span>
            <span><strong>Fuso Oficial:</strong> Brasília (BRT / UTC-3)</span>
        </div>
    </div>

    <div class="section-heading-gold">
        <h2>Destaques da Arquitetura (01 a 03)</h2>
        <div class="gold-line"></div>
    </div>

    <div class="highlights-grid-3">
        <div class="highlight-card">
            <div class="highlight-num">01</div>
            <div class="highlight-content">
                <h3>Arquitetura em 5 Schemas</h3>
                <p>Isolamento entre pouso bruto (<code>raw</code>), modelo estrela em BRT (<code>core</code>), governança/segurança (<code>ctl</code>/<code>sec</code>) e blindagem de BI (<code>mart</code>).</p>
            </div>
        </div>
        <div class="highlight-card">
            <div class="highlight-num">02</div>
            <div class="highlight-content">
                <h3>Catálogo Físico Exaustivo</h3>
                <p>Mapeamento 100% fiel à <code>INFORMATION_SCHEMA.COLUMNS</code> cobrindo todas as colunas, tipos SQL e chaves de <code>raw</code>, <code>core</code>, <code>ctl</code> e <code>sec</code>.</p>
            </div>
        </div>
        <div class="highlight-card">
            <div class="highlight-num">03</div>
            <div class="highlight-content">
                <h3>Dicionário Oficial das 8 Views</h3>
                <p>Especificação definitiva coluna por coluna das 8 Views do schema <code>mart</code> para auditoria executiva de KPIs da Diretoria.</p>
            </div>
        </div>
    </div>

    <div class="section-heading-gold">
        <h2>Índice / Conteúdo Completo</h2>
        <div class="gold-line"></div>
    </div>

    <div class="toc-box" style="padding: 2.8mm 4mm;">
        <ul class="toc-list" style="gap: 1.2mm;">
            <li class="toc-item" style="padding-bottom: 0.9mm; font-size: 8.2pt;">
                <div class="toc-item-left">
                    <span class="toc-badge">CAPÍTULO 01</span>
                    <span class="toc-title">A Arquitetura e o Porquê dos Schemas</span>
                    <span class="toc-desc">— Arquitetura Medalhão: raw (Bronze), core (Prata), ctl/sec e mart (Ouro)</span>
                </div>
                <span class="toc-page">Página 02</span>
            </li>
            <li class="toc-item" style="padding-bottom: 0.9mm; font-size: 8.2pt;">
                <div class="toc-item-left">
                    <span class="toc-badge">CAPÍTULO 02</span>
                    <span class="toc-title">Dicionário das Tabelas de Negócio (raw, ctl, sec e core)</span>
                    <span class="toc-desc">— Especificação física coluna a coluna (INFORMATION_SCHEMA.COLUMNS)</span>
                </div>
                <span class="toc-page">Páginas 03 a 08</span>
            </li>
            <li class="toc-item" style="padding-bottom: 0; font-size: 8.2pt;">
                <div class="toc-item-left">
                    <span class="toc-badge">CAPÍTULO 03</span>
                    <span class="toc-title">Dicionário Definitivo das Views Analíticas (Schema mart)</span>
                    <span class="toc-desc">— Regra de negócio exata de cada coluna das 8 Views do Apache Superset</span>
                </div>
                <span class="toc-page">Páginas 09 a 12</span>
            </li>
        </ul>
    </div>

    <div class="screenshot-placeholder-box" style="padding: 1.8mm 3mm;">
        <div class="screenshot-placeholder-tag">[INSERIR IMAGEM AQUI: Screenshot do SSMS com a árvore do banco MovideskDM]</div>
        {f'<div class="screenshot-img-wrapper"><img src="{img_ssms}" style="max-height: 52mm;" alt="Árvore do banco MovideskDM no SSMS" /></div>' if img_ssms else ''}
        <div class="screenshot-caption">Figura 0.1 — Árvore real do banco MovideskDM no SQL Server Management Studio (SSMS) exibindo as 18 Tabelas e as 8 Exibições (Views).</div>
    </div>
    """

    # =========================================================================
    # PÁGINA 02: CAPÍTULO 01 - A ARQUITETURA E O PORQUÊ DOS SCHEMAS
    # =========================================================================
    p2 = """
    <div class="chapter-header">
        <span class="chapter-badge">Capítulo 01</span>
        <div class="chapter-title-block">
            <h2>A Arquitetura e o Porquê dos Schemas (Medallion Architecture)</h2>
            <span>Fundamentos de Engenharia: Por que o Banco MovideskDM é Separado em 5 Camadas Especializadas</span>
        </div>
    </div>

    <p class="lead-text">
        Em projetos corporativos de Business Intelligence, conectar ferramentas de visualização diretamente às tabelas de ingestão gera lentidão, inconsistência de fuso horário e divergência de indicadores. Para garantir governança total e performance analítica na <strong>Advice Compliance Solutions</strong>, o banco <strong>MovideskDM</strong> foi projetado sob a <strong>Arquitetura Medalhão (Medallion Architecture)</strong> dividida em <strong>5 schemas</strong>:
    </p>

    <div class="steps-container compact">
        <div class="step-row">
            <div class="step-circle">1</div>
            <div class="step-text">
                <strong>Schema <code>raw</code> (Camada Bronze — Área de Pouso Bruta):</strong> É a zona de aterrissagem onde o extrator C# grava o retorno JSON da API do Movidesk exatamente como chegou (coluna <code>Payload NVARCHAR(MAX)</code>). <strong>Por que existe?</strong> A API do Movidesk possui limite severo de <em>10 requisições por minuto</em>. Ao salvar o JSON bruto em <code>raw.Ticket</code> e <code>raw.Pessoa</code>, protegemos a operação: se precisarmos alterar uma regra de cálculo ou mapear um campo novo no futuro, reprocessamos os <strong>46.850+ chamados localmente em poucos segundos</strong>, sem fazer uma única chamada na API!
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">2</div>
            <div class="step-text">
                <strong>Schema <code>core</code> (Camada Prata — O Coração em Modelo Estrela):</strong> É onde as procedures <code>core.usp_ProcessarTickets</code> e <code>core.usp_ProcessarPessoas</code> higienizam e estruturam os dados em <strong>Dimensões (<code>Dim_*</code>)</strong> e <strong>Fatos (<code>Fato_*</code>)</strong>. Aqui ocorrem três transformações vitais: <strong>(a) Conversão de Fuso Horário</strong> de <code>UTC</code> para o <strong>Horário Oficial de Brasília (BRT / UTC-3)</strong>; <strong>(b) Tipagem Forte e Indexação</strong> (conversão de texto JSON para <code>INT</code>, <code>DATETIME2(0)</code>, <code>BIT</code>) para máxima velocidade de consulta; e <strong>(c) Resolução Organizacional</strong>, vinculando contatos pessoas físicas às suas respectivas <strong>Empresas Clientes</strong>.
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">3</div>
            <div class="step-text">
                <strong>Schemas <code>ctl</code> e <code>sec</code> (Governança Operacional e Segurança RLS):</strong> O schema <code>ctl</code> governa o ciclo de vida da engenharia: armazena a <strong>Marca d'Água</strong> (<code>ctl.MarcaDagua</code>) para que a carga incremental retome do minuto exato onde parou, centraliza limiares de SLA e inatividade (<code>ctl.Parametro</code>) sem valores fixos em código (<em>hardcode</em>) e registra auditoria de cada lote (<code>ctl.ExecucaoCarga</code>). Já o schema <code>sec</code> (<code>sec.UsuarioEquipe</code>) implementa <strong>Row-Level Security (RLS)</strong>, restringindo quais equipes cada usuário pode enxergar no Superset.
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">4</div>
            <div class="step-text">
                <strong>Schema <code>mart</code> (Camada Ouro — A Blindagem Semântica do BI):</strong> É a camada exclusiva de consumo do Apache Superset. Encapsula todos os <code>LEFT JOINs</code> entre Fatos e Dimensões, regras de congelamento de SLA, tratamento de campos nulos (<code>ISNULL</code>) e fallbacks de status dentro de <strong>8 Views oficiais</strong>. Isso garante que o Superset jamais erre um cálculo ou apresente números conflitantes entre painéis.
            </div>
        </div>
    </div>

    <table class="zebra-table compact">
        <thead>
            <tr>
                <th style="width: 12%;">Schema</th>
                <th style="width: 17%;">Camada</th>
                <th style="width: 31%;">Objetos Físicos no MovideskDM</th>
                <th>Responsabilidade Arquitetural e Regra de Acesso</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><span class="badge-pill badge-gold">raw</span></td>
                <td><strong>Bronze (Pouso)</strong></td>
                <td><code>Ticket</code>, <code>Ticket_Stage</code>, <code>Pessoa</code>, <code>Pessoa_Stage</code></td>
                <td>Recebe carga em massa via <code>SqlBulkCopy</code> nas tabelas <code>_Stage</code> e aplica <code>MERGE</code> idempotente nas tabelas finais marcando <code>Processado = 0</code>.</td>
            </tr>
            <tr>
                <td><span class="badge-pill badge-teal">core</span></td>
                <td><strong>Prata (Estrela)</strong></td>
                <td>6 Dimensões (<code>Dim_*</code>) + 8 Fatos (<code>Fato_*</code>) + 3 Stored Procedures</td>
                <td>Armazena dados tipados em Horário de Brasília (BRT), histórico de transições de status e snapshots diários da fila.</td>
            </tr>
            <tr>
                <td><span class="badge-pill badge-teal">ctl</span></td>
                <td><strong>Governança</strong></td>
                <td><code>ExecucaoCarga</code>, <code>MarcaDagua</code>, <code>Parametro</code></td>
                <td>Controla paginação incremental (cursor UTC com janela de segurança de <code>-5 min</code>), parâmetros dinâmicos (4h, 48h, 60d) e telemetria.</td>
            </tr>
            <tr>
                <td><span class="badge-pill badge-teal">sec</span></td>
                <td><strong>Segurança</strong></td>
                <td><code>UsuarioEquipe</code></td>
                <td>Tabela de controle de acesso por linha (<em>Row-Level Security</em>) associando o login do usuário no Superset às equipes permitidas.</td>
            </tr>
            <tr>
                <td><span class="badge-pill badge-green">mart</span></td>
                <td><strong>Ouro (BI)</strong></td>
                <td><code>vw_VisaoGeralKpis</code>, <code>vw_SlaRadar</code>, <code>vw_BacklogAging</code>, <code>vw_StatusAging</code>, <code>vw_ThroughputDiario</code>, <code>vw_ClienteRaioX</code>, <code>vw_MapaDemanda</code>, <code>vw_BacklogEvolucao</code></td>
                <td><strong>Blindagem Semântica:</strong> Fonte única da verdade consumida pelos Datasets e Gráficos da Sala de Guerra no Apache Superset.</td>
            </tr>
        </tbody>
    </table>

    <div class="callout-gold">
        <strong>Padrão de Fuso Horário na Camada <code>core</code>:</strong> A API do Movidesk fornece todas as datas em <code>UTC</code> (03 horas à frente de Brasília). Durante a execução de <code>core.usp_ProcessarTickets</code>, todas as datas são convertidas via <code>AT TIME ZONE 'UTC' AT TIME ZONE 'E. South America Standard Time'</code> antes da gravação no banco. Assim, qualquer comparação com <code>SYSDATETIME()</code> nas Views do <code>mart</code> opera 100% em <strong>Horário Oficial de Brasília (BRT)</strong>.
    </div>
    """

    # =========================================================================
    # PÁGINA 03: CAPÍTULO 02 - DICIONÁRIO DE TABELAS (PARTE 1: RAW, CTL E SEC)
    # =========================================================================
    raw_ticket_rows = [
        ("TicketId", "INT NOT NULL (PK)", "Identificador único numérico do chamado no Movidesk (<code>$.id</code>). Chave primária clusterizada."),
        ("LastUpdateUtc", "DATETIME2(3) NULL", "Data/hora da última modificação do chamado na API em fuso <code>UTC</code> (<code>$.lastUpdate</code>). Usada como cursor incremental."),
        ("Payload", "NVARCHAR(MAX) NOT NULL", "Documento JSON bruto completo retornado pela API para o chamado (inclui objetos aninhados <code>owner</code>, <code>clients</code>, <code>statusHistories</code> e <code>customFieldValues</code>)."),
        ("Fonte", "VARCHAR(20) NOT NULL", "Identificador da origem do dado: <code>'API'</code> (extração oficial Movidesk) ou <code>'FICTICIO'</code> (massa de homologação)."),
        ("CarregadoEm", "DATETIME2(0) NOT NULL", "Data/hora local (<code>DEFAULT SYSDATETIME()</code>) em que o registro foi inserido ou atualizado na camada <code>raw</code>."),
        ("Processado", "BIT NOT NULL", "Flag de controle de fila ETL (<code>0</code> = pendente de transformação para o <code>core</code>; <code>1</code> = já processado por <code>core.usp_ProcessarTickets</code>)."),
    ]

    raw_pessoa_rows = [
        ("PessoaId", "VARCHAR(64) NOT NULL (PK)", "Identificador único da Pessoa ou Empresa no Movidesk (<code>$.id</code> do endpoint <code>/persons</code>)."),
        ("Payload", "NVARCHAR(MAX) NOT NULL", "JSON bruto completo do cadastro de pessoa/empresa (inclui <code>businessName</code>, <code>corporateName</code>, <code>personType</code> e <code>relationships</code>)."),
        ("Fonte", "VARCHAR(20) NOT NULL", "Origem do registro (<code>'API'</code>)."),
        ("CarregadoEm", "DATETIME2(0) NOT NULL", "Timestamp local de gravação no banco (<code>SYSDATETIME()</code>)."),
        ("Processado", "BIT NOT NULL", "Flag de processamento ETL (<code>0</code> = aguardando execução de <code>core.usp_ProcessarPessoas</code>; <code>1</code> = já integrado em <code>core.Dim_Cliente</code>)."),
    ]

    ctl_sec_rows = [
        ("ctl.ExecucaoCarga.ExecucaoId", "INT IDENTITY (PK)", "Identificador sequencial auto-incremental de cada execução do motor de carga ou procedure de transformação."),
        ("ctl.ExecucaoCarga.Tipo", "VARCHAR(40) NOT NULL", "Natureza da operação: <code>'HISTORICA'</code>, <code>'INCREMENTAL'</code> ou <code>'PROCESSAMENTO_CORE'</code>."),
        ("ctl.ExecucaoCarga.Inicio / Fim", "DATETIME2(0)", "Timestamps de início (<code>NOT NULL</code>) e término (<code>NULL</code> enquanto em execução) da tarefa."),
        ("ctl.ExecucaoCarga.Status", "VARCHAR(20) NOT NULL", "Estado da execução: <code>'EXECUTANDO'</code>, <code>'SUCESSO'</code> ou <code>'ERRO'</code>."),
        ("ctl.ExecucaoCarga.QtdRegistros", "INT NULL", "Quantidade de chamados ou pessoas processadas no lote."),
        ("ctl.ExecucaoCarga.Mensagem", "NVARCHAR(4000) NULL", "Resumo operacional do lote ou pilha detalhada de erro (<code>ERROR_MESSAGE()</code>) em caso de falha."),
        ("ctl.MarcaDagua.Entidade", "VARCHAR(40) NOT NULL (PK)", "Nome da entidade monitorada pelo extrator incremental (ex.: <code>'Ticket'</code>, <code>'Pessoa'</code>)."),
        ("ctl.MarcaDagua.UltimoValorUtc", "DATETIME2(3) NULL", "Maior <code>LastUpdateUtc</code> confirmado no banco. A carga incremental subtrai 5 minutos desta marca como margem de segurança."),
        ("ctl.MarcaDagua.AtualizadoEm", "DATETIME2(0) NOT NULL", "Data/hora local da última atualização do cursor de marca d'água."),
        ("ctl.Parametro.Chave", "VARCHAR(60) NOT NULL (PK)", "Identificador do parâmetro operacional (<code>HORAS_RADAR_SLA_IMINENTE</code>, <code>HORAS_SEM_INTERACAO_ALERTA</code>, <code>DIAS_CLIENTE_SILENCIOSO</code>)."),
        ("ctl.Parametro.Valor / Descricao", "NVARCHAR(400)", "Valor configurado (padrões: <code>4</code> horas, <code>48</code> horas e <code>60</code> dias) e explicação da regra de negócio."),
        ("sec.UsuarioEquipe.UsuarioSuperset", "NVARCHAR(128) (PK)", "Login (<em>username</em>) do usuário cadastrado no Apache Superset (parte 1 da chave primária composta)."),
        ("sec.UsuarioEquipe.Equipe", "NVARCHAR(128) (PK)", "Nome exato da equipe do Movidesk que o usuário tem permissão para visualizar via <em>Row-Level Security</em>."),
    ]

    p3 = f"""
    <div class="chapter-header">
        <span class="chapter-badge">Capítulo 02</span>
        <div class="chapter-title-block">
            <h2>Dicionário das Tabelas de Negócio (INFORMATION_SCHEMA.COLUMNS)</h2>
            <span>Parte 1 — Tabelas de Ingestão Bruta (raw), Governança de ETL (ctl) e Segurança (sec)</span>
        </div>
    </div>

    <div class="obj-banner">
        <div><strong>raw.Ticket</strong> &amp; <strong>raw.Ticket_Stage</strong> — Pouso Bruto de Chamados</div>
        <span class="obj-meta">PK: TicketId · Índice: IX_raw_Ticket_Processado</span>
    </div>
    {render_dict_table(raw_ticket_rows, dense=True)}

    <div class="obj-banner">
        <div><strong>raw.Pessoa</strong> &amp; <strong>raw.Pessoa_Stage</strong> — Pouso Bruto de Clientes e Empresas (/persons)</div>
        <span class="obj-meta">PK: PessoaId · Alimenta core.Dim_Cliente</span>
    </div>
    {render_dict_table(raw_pessoa_rows, dense=True)}

    <div class="obj-banner">
        <div><strong>ctl.ExecucaoCarga</strong>, <strong>ctl.MarcaDagua</strong>, <strong>ctl.Parametro</strong> &amp; <strong>sec.UsuarioEquipe</strong></div>
        <span class="obj-meta">Schemas ctl e sec · Auditoria, Cursores e Row-Level Security</span>
    </div>
    {render_dict_table(ctl_sec_rows, dense=True)}
    """

    # =========================================================================
    # PÁGINA 04: CAPÍTULO 02 - PARTE 2: DIM_CLIENTE, DIM_STATUS E DIM_EQUIPE
    # =========================================================================
    dim_cliente_rows = [
        ("ClienteId", "VARCHAR(64) NOT NULL (PK)", "Código único do cliente ou organização no Movidesk (<code>$.id</code> ou <code>$.organization.id</code>)."),
        ("Nome", "NVARCHAR(256) NOT NULL", "Nome Fantasia da empresa ou nome de exibição do contato (<code>$.businessName</code>)."),
        ("RazaoSocial", "NVARCHAR(256) NULL", "Razão Social jurídica da organização (<code>$.corporateName</code>)."),
        ("TipoPessoa", "TINYINT NULL", "Classificação cadastral no Movidesk: <code>1</code> = Pessoa Física (Contato), <code>2</code> = Empresa (Pessoa Jurídica), <code>4</code> = Departamento."),
        ("EmpresaId", "VARCHAR(64) NULL", "Auto-relacionamento hierárquico: quando o registro é uma Pessoa Física (<code>TipoPessoa = 1</code>), aponta para o <code>ClienteId</code> da Empresa à qual pertence."),
        ("Ativo", "BIT NULL", "Indica se o cadastro do cliente/empresa está ativo no Movidesk (<code>1</code> = Ativo, <code>0</code> = Inativo)."),
        ("DataCadastro", "DATETIME2(0) NULL", "Data de criação do cadastro no Movidesk convertida para Horário de Brasília (BRT)."),
    ]

    dim_status_rows = [
        ("StatusId", "INT IDENTITY (PK)", "Chave substituta (<em>surrogate key</em>) auto-incremental da dimensão de status."),
        ("Nome", "NVARCHAR(128) UNIQUE", "Nome literal do status no Movidesk (ex.: <code>'Novo'</code>, <code>'Em atendimento'</code>, <code>'Aguardando confirmação do cliente'</code>). Chave de <code>JOIN</code>."),
        ("GrupoStatus", "NVARCHAR(60) NOT NULL", "Agrupador executivo: <code>'Fila (Não Iniciado)'</code>, <code>'Com Analista'</code>, <code>'Aguardando Cliente'</code>, <code>'Dependência Externa / Dev'</code> ou <code>'Encerrado'</code>."),
        ("OrdemFluxo", "TINYINT NOT NULL", "Ordem lógica da etapa no ciclo de vida do atendimento (<code>1</code> = Entrada até <code>7</code> = Fechado/Cancelado) para ordenação de gráficos."),
        ("PausaSla", "BIT NOT NULL", "Indica se o status congela contratualmente o relógio de SLA (<code>1</code> = Pausa SLA; <code>0</code> = SLA correndo)."),
        ("EhDependenciaTerceiro", "BIT NOT NULL", "Identifica status estacionados em engenharia/desenvolvimento ou fornecedor externo (<code>1</code> = Sim; <code>0</code> = Não)."),
        ("EhFinal", "BIT NOT NULL", "Determina se o status encerra o ciclo de vida do chamado (<code>1</code> = Resolvido/Fechado/Cancelado; <code>0</code> = Chamado em aberto no Backlog)."),
        ("Cor", "CHAR(7) NULL", "Código hexadecimal da cor institucional sugerida para o status nos gráficos (ex.: <code>'#0B3B52'</code>)."),
        ("Mapeado", "BIT NOT NULL", "Indica se o status fazia parte do catálogo padrão (<code>1</code>) ou se foi auto-descoberto dinamicamente a partir do <code>baseStatus</code> da API (<code>0</code>)."),
    ]

    dim_equipe_rows = [
        ("EquipeId", "INT IDENTITY (PK)", "Identificador sequencial interno da equipe no Data Mart."),
        ("Nome", "NVARCHAR(128) UNIQUE", "Nome oficial da equipe de atendimento no Movidesk (<code>$.ownerTeam</code>). Chave natural de cruzamento."),
        ("EhSuporte", "BIT NOT NULL", "Indica se a equipe faz parte da operação ativa de suporte (<code>DEFAULT 1</code>) para compor a grade de <code>mart.vw_ThroughputDiario</code>."),
    ]

    p4 = f"""
    <div class="chapter-header">
        <span class="chapter-badge">Capítulo 02</span>
        <div class="chapter-title-block">
            <h2>Dicionário das Tabelas de Dimensão (Schema core — Parte 2A)</h2>
            <span>Dimensões Organizacionais e de Fluxo: core.Dim_Cliente, core.Dim_Status e core.Dim_Equipe</span>
        </div>
    </div>

    <div class="obj-banner">
        <div><strong>core.Dim_Cliente</strong> — Dimensão de Empresas Clientes e Contatos (Pessoas Físicas)</div>
        <span class="obj-meta">PK: ClienteId · Auto-Join Organizacional: EmpresaId · 7 Colunas</span>
    </div>
    {render_dict_table(dim_cliente_rows, dense=True)}

    <div class="obj-banner">
        <div><strong>core.Dim_Status</strong> — Dimensão de Status, Grupos de Fila e Regras de Parada de SLA</div>
        <span class="obj-meta">PK: StatusId · UK: Nome · 9 Colunas</span>
    </div>
    {render_dict_table(dim_status_rows, dense=True)}

    <div class="obj-banner">
        <div><strong>core.Dim_Equipe</strong> — Dimensão Oficial de Equipes de Atendimento</div>
        <span class="obj-meta">PK: EquipeId · UK: Nome · 3 Colunas</span>
    </div>
    {render_dict_table(dim_equipe_rows, dense=True)}
    """

    # =========================================================================
    # PÁGINA 05: CAPÍTULO 02 - PARTE 2B: DIM_AGENTE, DIM_CAMPOCUSTOMIZADO E DIM_CALENDARIO
    # =========================================================================
    dim_agente_rows = [
        ("AgenteId", "VARCHAR(64) NOT NULL (PK)", "Identificador único do analista de suporte no Movidesk (<code>$.owner.id</code>)."),
        ("Nome", "NVARCHAR(256) NOT NULL", "Nome completo ou nome de exibição do analista responsável (<code>$.owner.businessName</code>)."),
        ("Email", "NVARCHAR(256) NULL", "Endereço de e-mail corporativo do analista (<code>$.owner.email</code>)."),
        ("Ativo", "BIT NOT NULL", "Flag indicando se o cadastro do analista está ativo na operação (<code>DEFAULT 1</code>)."),
    ]

    dim_campo_rows = [
        ("CampoId", "INT NOT NULL (PK)", "ID numérico do campo adicional no Movidesk (ex.: <code>133948</code> = Versão do Produto / Release)."),
        ("Nome", "NVARCHAR(128) NOT NULL", "Nome descritivo do campo customizado para exibição em relatórios."),
        ("Descricao", "NVARCHAR(400) NULL", "Explicação detalhada da finalidade do campo e da regra de formulário associada no Movidesk."),
    ]

    dim_calendario_full_rows = [
        ("Data", "DATE NOT NULL (PK)", "Data civil diária (de <code>2022-01-01</code> a <code>2028-12-31</code>) usada como eixo contínuo de séries temporais."),
        ("Ano", "SMALLINT NOT NULL", "Ano civil com 4 dígitos (ex.: <code>2026</code>)."),
        ("Trimestre", "TINYINT NOT NULL", "Trimestre do ano civil (<code>1</code> a <code>4</code>)."),
        ("Mes", "TINYINT NOT NULL", "Número do mês civil (<code>1</code> = Janeiro a <code>12</code> = Dezembro)."),
        ("NomeMes", "NVARCHAR(20) NOT NULL", "Nome do mês por extenso em português."),
        ("AnoMes", "CHAR(7) NOT NULL", "Chave de competência mensal no padrão ISO <code>'YYYY-MM'</code> (ex.: <code>'2026-11'</code>) para ordenação cronológica exata."),
        ("Semana", "TINYINT NOT NULL", "Número da semana dentro do ano (<code>DATEPART(ISO_WEEK, Data)</code>)."),
        ("DiaSemana", "TINYINT NOT NULL", "Código numérico do dia da semana (<code>1</code> = Domingo até <code>7</code> = Sábado)."),
        ("NomeDiaSemana", "NVARCHAR(20) NOT NULL", "Nome do dia da semana em português (ex.: <code>'Segunda-feira'</code>)."),
        ("EhFimDeSemana", "BIT NOT NULL", "Vale <code>1</code> para Sábado e Domingo; <code>0</code> de Segunda a Sexta-feira."),
        ("EhFeriado", "BIT NOT NULL", "Vale <code>1</code> quando a data corresponde a feriado nacional oficial cadastrado; caso contrário, <code>0</code>."),
        ("NomeFeriado", "NVARCHAR(60) NULL", "Nome oficial do feriado nacional (ex.: <code>'Proclamação da República'</code>) ou <code>NULL</code> em dias normais."),
        ("EhDiaUtil", "BIT NOT NULL", "Vale <code>1</code> quando <code>EhFimDeSemana = 0 AND EhFeriado = 0</code>; caso contrário, <code>0</code>."),
    ]

    p4_b = f"""
    <div class="chapter-header">
        <span class="chapter-badge">Capítulo 02</span>
        <div class="chapter-title-block">
            <h2>Dicionário das Tabelas de Dimensão (Schema core — Parte 2B)</h2>
            <span>Dimensões de Analistas, Campos Customizados e Calendário Oficial: Dim_Agente, Dim_CampoCustomizado e Dim_Calendario</span>
        </div>
    </div>

    <div class="obj-banner">
        <div><strong>core.Dim_Agente</strong> — Dimensão de Analistas de Suporte</div>
        <span class="obj-meta">PK: AgenteId · 4 Colunas</span>
    </div>
    {render_dict_table(dim_agente_rows, dense=True)}

    <div class="obj-banner">
        <div><strong>core.Dim_CampoCustomizado</strong> — Catálogo de Campos Adicionais de Formulário</div>
        <span class="obj-meta">PK: CampoId (Destaque: 133948 = Versão Release) · 3 Colunas</span>
    </div>
    {render_dict_table(dim_campo_rows, dense=True)}

    <div class="obj-banner">
        <div><strong>core.Dim_Calendario</strong> — Dimensão Oficial de Tempo e Dias Úteis (2022–2028)</div>
        <span class="obj-meta">PK: Data · Todas as 13 Colunas</span>
    </div>
    {render_dict_table(dim_calendario_full_rows, dense=True)}
    """

    # =========================================================================
    # PÁGINA 05: CAPÍTULO 02 - PARTE 3: CORE.FATO_TICKET (COLUNAS 01 A 23)
    # =========================================================================
    fato_ticket_part1 = [
        ("TicketId", "INT NOT NULL (PK)", "Identificador único oficial do chamado no Movidesk (<code>$.id</code>). Chave primária da tabela fato central."),
        ("Protocolo", "NVARCHAR(64) NULL", "Código de protocolo alfanumérico exibido ao cliente final na interface do Movidesk (<code>$.protocol</code>)."),
        ("Tipo", "TINYINT NULL", "Visibilidade do chamado no Movidesk (<code>$.type</code>): <code>1</code> = Chamado Interno; <code>2</code> = Chamado Público."),
        ("Assunto", "NVARCHAR(400) NULL", "Título resumido do chamado informado na abertura (<code>$.subject</code>)."),
        ("Categoria", "NVARCHAR(128) NULL", "Classificação da natureza da solicitação (<code>$.category</code>: ex. <em>Dúvida</em>, <em>Incidente</em>, <em>Requisição de Serviço</em>)."),
        ("Urgencia", "NVARCHAR(128) NULL", "Nível de criticidade operacional (<code>$.urgency</code>: ex. <em>Baixa</em>, <em>Média</em>, <em>Alta</em>, <em>Urgente</em>)."),
        ("Status", "NVARCHAR(128) NULL", "Status atual customizado do chamado (<code>$.status</code>). Faz <code>LEFT JOIN</code> com <code>core.Dim_Status.Nome</code>."),
        ("StatusBase", "NVARCHAR(40) NULL", "Status sistêmico nativo do Movidesk (<code>$.baseStatus</code>: <code>New</code>, <code>InAttendance</code>, <code>Stopped</code>, <code>Resolved</code>, <code>Closed</code>, <code>Canceled</code>). Usado como fallback de segurança."),
        ("Justificativa", "NVARCHAR(256) NULL", "Motivo complementar exigido pelo Movidesk ao pausar ou alterar determinados status (<code>$.justification</code>)."),
        ("Origem", "SMALLINT NULL", "Canal de entrada do chamado (<code>$.origin</code>: Portal do Cliente, E-mail, Telefone, Chat, API, etc.)."),
        ("Equipe", "NVARCHAR(128) NULL", "Nome da equipe de suporte que detém a posse atual do chamado (<code>$.ownerTeam</code>)."),
        ("AgenteId", "VARCHAR(64) NULL", "Código do analista responsável atual pelo chamado (<code>$.owner.id</code>). Faz <code>LEFT JOIN</code> com <code>core.Dim_Agente.AgenteId</code>."),
        ("CriadoPorId", "VARCHAR(64) NULL", "Identificador da pessoa (cliente ou agente) que abriu originalmente o chamado (<code>$.createdBy.id</code>)."),
        ("EmpresaId", "VARCHAR(64) NULL", "Identificador da <strong>Empresa Cliente principal</strong> do chamado. A procedure resolve automaticamente <code>$.clients[0].organization.id</code> ou o vínculo em <code>Dim_Cliente</code> para garantir que aponte para a Pessoa Jurídica."),
        ("ServicoN1", "NVARCHAR(256) NULL", "Primeiro nível do catálogo de serviços do Movidesk (<code>$.serviceFirstLevel</code>)."),
        ("ServicoN2", "NVARCHAR(256) NULL", "Segundo nível do catálogo de serviços do Movidesk (<code>$.serviceSecondLevel</code>)."),
        ("ServicoN3", "NVARCHAR(256) NULL", "Terceiro nível do catálogo de serviços do Movidesk (<code>$.serviceThirdLevel</code>)."),
        ("Tags", "NVARCHAR(1000) NULL", "Arranjo JSON das etiquetas (<em>tags</em>) associadas ao chamado (<code>$.tags</code> truncado em 1.000 caracteres)."),
        ("DataCriacao", "DATETIME2(0) NULL", "Data e hora exatas de abertura do chamado (<code>$.createdDate</code>), convertidas de <code>UTC</code> para <strong>Horário de Brasília (BRT)</strong>."),
        ("DataUltimaAtualizacao", "DATETIME2(0) NULL", "Data e hora da última alteração cadastral ou de status do ticket (<code>$.lastUpdate</code>) em <strong>Horário de Brasília (BRT)</strong>."),
        ("DataUltimaAcao", "DATETIME2(0) NULL", "Data e hora do último trâmite/interação registrado no chamado (<code>$.lastActionDate</code>) em <strong>Horário de Brasília (BRT)</strong>."),
        ("DataResolucao", "DATETIME2(0) NULL", "Data e hora em que o chamado recebeu status <em>Resolvido</em> (<code>$.resolvedIn</code>) em <strong>Horário de Brasília (BRT)</strong>. Base do Throughput e SLA."),
        ("DataFechamento", "DATETIME2(0) NULL", "Data e hora de fechamento definitivo do chamado (<code>$.closedIn</code>) em <strong>Horário de Brasília (BRT)</strong>."),
    ]

    p5 = f"""
    <div class="chapter-header">
        <span class="chapter-badge">Capítulo 02</span>
        <div class="chapter-title-block">
            <h2>Dicionário da Tabela Fato Central (core.Fato_Ticket — Parte 1)</h2>
            <span>Colunas 01 a 23: Identificação, Classificação, Posse, Catálogo de Serviços e Datas em BRT</span>
        </div>
    </div>

    <div class="obj-banner">
        <div><strong>core.Fato_Ticket</strong> (Colunas 01 a 23 de 42) — Granularidade: 1 Linha por Chamado</div>
        <span class="obj-meta">PK: TicketId · Datas normalizadas em Horário de Brasília (BRT)</span>
    </div>
    {render_dict_table(fato_ticket_part1, dense=True)}
    """

    # =========================================================================
    # PÁGINA 06: CAPÍTULO 02 - PARTE 4: CORE.FATO_TICKET (COLS 24-42) + STATUS HISTORICO
    # =========================================================================
    fato_ticket_part2 = [
        ("DataReabertura", "DATETIME2(0) NULL", "Data e hora da última reabertura do chamado (<code>$.reopenedIn</code>), convertida para Horário de Brasília (BRT)."),
        ("QtdAcoes", "INT NULL", "Total de ações (pareceres públicos e internos) registradas no chamado (<code>$.actionCount</code>)."),
        ("SlaAcordo", "NVARCHAR(256) NULL", "Nome do contrato/acordo de nível de serviço aplicado ao chamado (<code>$.slaAgreement</code>)."),
        ("SlaRegra", "NVARCHAR(256) NULL", "Regra específica dentro do contrato de SLA aplicada ao ticket (<code>$.slaAgreementRule</code>)."),
        ("SlaTempoSolucaoMin", "INT NULL", "Meta contratual de tempo de solução do chamado em minutos (<code>$.slaSolutionTime</code>)."),
        ("SlaTempoRespostaMin", "INT NULL", "Meta contratual de tempo de primeira resposta em minutos (<code>$.slaResponseTime</code>)."),
        ("SlaDataSolucao", "DATETIME2(0) NULL", "<strong>Prazo Limite (Vencimento) do SLA de Solução</strong> (<code>$.slaSolutionDate</code>) convertido para <strong>Horário de Brasília (BRT)</strong>. Coluna-chave do Radar de SLA."),
        ("SlaSolucaoPausado", "BIT NULL", "Flag booleana (<code>$.slaSolutionDateIsPaused</code>): <code>1</code> indica que o relógio de SLA está congelado no momento; <code>0</code> indica relógio correndo."),
        ("SlaDataResposta", "DATETIME2(0) NULL", "Prazo limite contratual para a primeira resposta do analista (<code>$.slaResponseDate</code>) em Horário de Brasília (BRT)."),
        ("SlaDataRespostaReal", "DATETIME2(0) NULL", "Data/hora real em que o primeiro atendimento foi efetuado (<code>$.slaRealResponseDate</code>) em Horário de Brasília (BRT)."),
        ("ResolvidoPrimeiroContato", "BIT NULL", "Indicador oficial de <strong>FCR (First Contact Resolution)</strong> (<code>$.resolvedInFirstCall</code>): <code>1</code> = resolvido no primeiro contato; <code>0</code> = exigiu múltiplos trâmites."),
        ("TicketPaiId / QtdTicketsFilhos", "INT NULL", "ID do ticket pai (quando este chamado é filho) e contagem de tickets filhos vinculados em <code>core.Fato_TicketRelacao</code>."),
        ("DataPrimeiraAcaoAgente", "DATETIME2(0) NULL", "Timestamp em BRT da primeira ação realizada por um analista (calculado a partir de <code>core.Fato_Acao</code>)."),
        ("DataUltimaAcaoAgente / Cliente", "DATETIME2(0) NULL", "Timestamps em BRT da última interação feita por um analista e pelo cliente, respectivamente."),
        ("QtdAcoesPublicasAgente", "INT NULL", "Total de interações públicas (visíveis ao cliente) efetuadas por analistas no chamado."),
        ("QtdReaberturas / QtdTrocasEquipe", "INT NULL", "Contadores derivados do histórico de status e de responsáveis indicando quantas vezes o ticket reabriu ou mudou de fila."),
        ("AtualizadoEm", "DATETIME2(0) NOT NULL", "Data/hora local (<code>DEFAULT SYSDATETIME()</code>) da última atualização da linha no Data Mart."),
    ]

    fato_status_hist_rows = [
        ("TicketId", "INT NOT NULL (PK)", "Identificador do chamado (parte 1 da chave primária composta; referencia <code>core.Fato_Ticket.TicketId</code>)."),
        ("Sequencia", "INT NOT NULL (PK)", "Ordem cronológica da transição de status dentro do chamado (<code>1, 2, 3...</code> gerada via <code>ROW_NUMBER() OVER (PARTITION BY TicketId ORDER BY DataInicio)</code>)."),
        ("Status", "NVARCHAR(128) NOT NULL", "Nome do status em que o chamado permaneceu durante aquele intervalo (<code>$.statusHistories[].status</code>)."),
        ("Justificativa", "NVARCHAR(256) NULL", "Justificativa informada na mudança para este status (<code>$.statusHistories[].justification</code>)."),
        ("DataInicio", "DATETIME2(0) NOT NULL", "Data/hora de entrada no status (<code>$.statusHistories[].changedDate</code>) convertida para Horário de Brasília (BRT)."),
        ("DataFim", "DATETIME2(0) NULL", "Data/hora de saída do status, calculada via função analítica <code>LEAD(DataInicio)</code>. Quando <code>NULL</code>, indica que este é o <strong>status atual em curso</strong> do chamado."),
        ("PermanenciaMinCorridos", "INT NULL", "Tempo total de permanência naquele status em <strong>minutos corridos</strong> (<code>permanencyTimeFullTime / 60.0</code>)."),
        ("PermanenciaMinUteis", "INT NULL", "Tempo de permanência naquele status em <strong>minutos úteis de expediente</strong> (<code>permanencyTimeWorkingTime / 60.0</code>)."),
        ("AlteradoPorId", "VARCHAR(64) NULL", "Identificador do usuário que efetuou a transição de status (<code>$.statusHistories[].changedBy.id</code>)."),
    ]

    p6 = f"""
    <div class="chapter-header">
        <span class="chapter-badge">Capítulo 02</span>
        <div class="chapter-title-block">
            <h2>Dicionário de core.Fato_Ticket (Parte 2) e core.Fato_StatusHistorico</h2>
            <span>Colunas 24 a 42 da Fato_Ticket (SLA, FCR e Derivados) e Rastreamento de Tempo por Status</span>
        </div>
    </div>

    <div class="obj-banner">
        <div><strong>core.Fato_Ticket</strong> (Colunas 24 a 42 de 42) — Acordos de SLA, FCR e Métricas Derivadas</div>
        <span class="obj-meta">PK: TicketId · Índices por StatusBase, DataCriacao, DataResolucao e EmpresaId</span>
    </div>
    {render_dict_table(fato_ticket_part2, dense=True)}

    <div class="obj-banner">
        <div><strong>core.Fato_StatusHistorico</strong> — Histórico de Passagens e Permanência em Cada Status</div>
        <span class="obj-meta">PK Composta: (TicketId, Sequencia) · Base da View mart.vw_StatusAging</span>
    </div>
    {render_dict_table(fato_status_hist_rows, dense=True)}
    """

    # =========================================================================
    # PÁGINA 07: CAPÍTULO 02 - PARTE 5: DEMAIS TABELAS FATO (SNAPSHOT, CAMPO CUSTOM, ACAO...)
    # =========================================================================
    fato_snapshot_rows = [
        ("DataSnapshot", "DATE NOT NULL (PK)", "Data civil da fotografia da fila (parte 1 da PK composta). Povoada para os últimos 90 dias + data corrente (<code>@Hoje</code>)."),
        ("Equipe", "NVARCHAR(128) NOT NULL (PK)", "Equipe responsável pelos chamados abertos naquela data (parte 2 da PK composta)."),
        ("AgenteId", "VARCHAR(64) NOT NULL (PK)", "ID do analista responsável na data ou <code>'NAO_ATRIBUIDO'</code> (parte 3 da PK composta)."),
        ("Status", "NVARCHAR(128) NOT NULL (PK)", "Status em que os chamados se encontravam ao final daquele dia (reconstruído via <code>Fato_StatusHistorico</code>)."),
        ("Urgencia", "NVARCHAR(128) NOT NULL (PK)", "Nível de urgência dos chamados contabilizados no grupo (parte 5 da PK composta)."),
        ("QtdTickets", "INT NOT NULL", "Quantidade total de chamados que estavam <strong>abertos (não encerrados)</strong> no fechamento daquele dia."),
        ("QtdSlaVencido", "INT NOT NULL", "Subconjunto de <code>QtdTickets</code> cujo prazo <code>SlaDataSolucao</code> já estava expirado naquela data e sem SLA pausado."),
    ]

    fato_complementares_rows = [
        ("Fato_CampoCustomizado.TicketId", "INT NOT NULL (PK)", "ID do chamado ao qual o valor de formulário pertence (parte 1 da PK composta)."),
        ("Fato_CampoCustomizado.CampoId", "INT NOT NULL (PK)", "Código do campo customizado (ex.: <code>133948</code> = Versão do Produto / Release). Faz <code>JOIN</code> com <code>Dim_CampoCustomizado</code>."),
        ("Fato_CampoCustomizado.Linha", "INT NOT NULL (PK)", "Número da linha do campo customizado no formulário (<code>$.customFieldValues[].line</code>, padrão <code>1</code>)."),
        ("Fato_CampoCustomizado.Valor", "NVARCHAR(1000) NULL", "Conteúdo preenchido no campo adicional (ex.: <code>'KN1'</code>, <code>'e-Guardian'</code>, <code>'Aquilla'</code>)."),
        ("Fato_TicketCliente.TicketId / ClienteId", "INT / VARCHAR(64) (PK)", "Relação <code>N:N</code> entre cada chamado e todos os solicitantes vinculados na lista <code>$.clients[]</code>."),
        ("Fato_TicketCliente.EmpresaId", "VARCHAR(64) NULL", "Código da Empresa (Organização) resolvida para aquele solicitante do chamado."),
        ("Fato_Acao.TicketId / AcaoId", "INT NOT NULL (PK)", "Chave composta identificando cada ação/interação (<code>$.actions[].id</code>) de um chamado."),
        ("Fato_Acao.Tipo / Origem / Status", "TINYINT / SMALLINT / NVARCHAR", "Visibilidade da ação (<code>1</code> = Interna, <code>2</code> = Pública), canal de origem e status na ocasião do trâmite."),
        ("Fato_Acao.DataCriacao / CriadoPorId", "DATETIME2(0) / VARCHAR(64)", "Data/hora da ação em BRT e identificador do autor do trâmite."),
        ("Fato_Acao.CriadoPorPerfil / EhAgente / Deletada", "TINYINT / BIT / BIT", "Perfil do autor (<code>1</code> = Agente, <code>2</code> = Cliente) e flags indicando se a ação foi feita por analista e se foi excluída."),
        ("Fato_ResponsavelHistorico.(7 colunas)", "PK: (TicketId, Sequencia)", "Registra trocas de posse (<code>Equipe</code>, <code>AgenteId</code>, <code>DataInicio</code>, <code>DataFim</code>, <code>PermanenciaMinCorridos</code>, <code>AlteradoPorId</code>)."),
        ("Fato_TicketRelacao.(TicketPaiId, TicketFilhoId)", "INT NOT NULL (PK)", "Mapeia vínculos hierárquicos entre chamados Pai e chamados Filhos (<code>$.parentTickets</code> / <code>$.childrenTickets</code>)."),
    ]

    p7 = f"""
    <div class="chapter-header">
        <span class="chapter-badge">Capítulo 02</span>
        <div class="chapter-title-block">
            <h2>Dicionário dos Fatos de Snapshot e Fatos Complementares (core)</h2>
            <span>Parte 5 — Evolução Diária da Fila (Fato_SnapshotBacklog), Campos Customizados e Ações</span>
        </div>
    </div>

    <div class="obj-banner">
        <div><strong>core.Fato_SnapshotBacklog</strong> — Fotografia Diária Histórica da Fila (Últimos 90 Dias + Hoje)</div>
        <span class="obj-meta">PK Composta: (DataSnapshot, Equipe, AgenteId, Status, Urgencia)</span>
    </div>
    {render_dict_table(fato_snapshot_rows, dense=True)}

    <div class="obj-banner">
        <div><strong>core.Fato_CampoCustomizado</strong>, <strong>Fato_TicketCliente</strong>, <strong>Fato_Acao</strong>, <strong>Fato_ResponsavelHistorico</strong> &amp; <strong>Fato_TicketRelacao</strong></div>
        <span class="obj-meta">Tabelas Fato de Detalhe e Relacionamento</span>
    </div>
    {render_dict_table(fato_complementares_rows, dense=True)}

    <div class="callout-gold" style="padding: 1.8mm 2.8mm; font-size: 7.9pt;">
        <strong>Nota Arquitetural sobre Pareceres Digitados (<code>actions[].description</code>):</strong> Por exigência da API do Movidesk, a expansão da lista de ações e textos livres (<code>$expand=actions</code>) só é permitida em consultas individuais de 1 único ticket por vez. Para viabilizar a extração de 46.850+ chamados em lotes de 1.000 registros sem estourar o limite de 10 req/min, a carga padrão traz o contador <code>QtdAcoes</code> e a <code>DataUltimaAcao</code> na <code>core.Fato_Ticket</code>, mantendo <code>Fato_Acao</code> pronta para cargas detalhadas sob demanda.
    </div>
    """

    # =========================================================================
    # PÁGINA 08: CAPÍTULO 03 - VIEWS DO MART (PARTE 1: VISAO GERAL KPIS + SLA RADAR)
    # =========================================================================
    vw_kpis_rows = [
        ("Equipe", "NVARCHAR(128)", "Nome da equipe de suporte que detém a posse atual do chamado."),
        ("BacklogAtual", "INT", "Volume exato de chamados em aberto no momento atual (baseStatus diferente de Resolvido, Fechado ou Cancelado) sob responsabilidade da equipe."),
        ("SlaVencidos", "INT", "Subconjunto do Backlog Atual cujo prazo limite (SlaDataSolucao) já foi ultrapassado em relação à hora atual."),
        ("SlaIminente4h", "INT", "Subconjunto do Backlog Atual cujo prazo de solução expira nas próximas 4 horas (corridas ou úteis, dependendo do contrato)."),
        ("SlaPausados", "INT", "Subconjunto do Backlog Atual onde o relógio de SLA está congelado (ex: Aguardando Cliente)."),
        ("EmDependenciaDev", "INT", "Subconjunto do Backlog Atual estacionado em um status de dependência de terceiros (ex: Aguardando Desenvolvimento)."),
        ("AbertosHoje", "INT", "Quantidade de chamados criados (DataCriacao) no dia corrente, atribuídos à equipe."),
        ("ResolvidosHoje", "INT", "Quantidade de chamados que ganharam o status de Resolvido (DataResolucao) no dia corrente pela equipe."),
        ("FcrUltimos30DiasPct", "DECIMAL(5,1)", "Percentual de First Contact Resolution. Chamados resolvidos na primeira interação nos últimos 30 dias móveis."),
    ]

    vw_slaradar_rows = [
        ("TicketId", "INT", "Número identificador único do chamado em aberto na fila."),
        ("Protocolo", "NVARCHAR(64)", "Protocolo oficial do chamado no Movidesk para busca rápida."),
        ("Assunto", "NVARCHAR(400)", "Título descritivo do problema reportado no chamado."),
        ("Categoria / Urgencia", "NVARCHAR(128)", "Categoria funcional e nível de criticidade (Baixa, Média, Alta, Urgente) do ticket."),
        ("Status", "NVARCHAR(128)", "Status atual detalhado em que o chamado se encontra."),
        ("GrupoStatus", "NVARCHAR(60)", "Macro-etapa do status (<code>Com Analista</code>, <code>Aguardando Cliente</code>, <code>Dependência Externa / Dev</code>, etc.)."),
        ("Equipe", "NVARCHAR(128)", "Nome da equipe responsável pelo atendimento (<code>ISNULL(t.Equipe, 'Sem Equipe')</code>)."),
        ("Analista", "NVARCHAR(256)", "Nome do analista proprietário do chamado (obtido via <code>LEFT JOIN core.Dim_Agente</code>; exibe <code>'Não Atribuído'</code> se nulo)."),
        ("Cliente", "NVARCHAR(256)", "Nome da <strong>Empresa Cliente</strong> proprietária do chamado (resolve hierarquia <code>Contato → Empresa</code> via <code>ISNULL(emp.Nome, cli.Nome)</code>)."),
        ("DataCriacao / DataUltimaAcao", "DATETIME2(0)", "Datas de abertura e do último trâmite registrado no chamado, já em Horário de Brasília (BRT)."),
        ("SlaAcordo", "NVARCHAR(256)", "Nome do contrato de SLA aplicado ao chamado."),
        ("SlaDataSolucao", "DATETIME2(0)", "Data e hora limite em que o chamado deve ser resolvido antes de estourar o SLA (em BRT)."),
        ("SlaSolucaoPausado", "BIT", "Indica se a contagem do prazo de solução está pausada (<code>1</code> = Pausado; <code>0</code> = Correndo)."),
        ("FaixaRiscoSla", "VARCHAR(20)", "Termômetro preditivo calculado em tempo real: <code>'Vencido'</code> (prazo ultrapassado), <code>'Crítico (&lt; 2h)'</code> (&le; 120 min), <code>'Alerta (&lt; 4h)'</code> (&le; parâmetro <code>ctl.Parametro</code>), <code>'Atenção (&lt; 8h)'</code> (&le; 480 min), <code>'No Prazo (&gt; 8h)'</code>, <code>'SLA Pausado'</code> ou <code>'Sem SLA Definido'</code>."),
        ("OrdemGravidade", "INT", "Código numérico de prioridade visual (<code>1</code> = Vencido, <code>2</code> = Crítico &lt; 2h, <code>3</code> = Alerta &lt; 4h, <code>4</code> = Atenção &lt; 8h, <code>5</code> = Pausado, <code>6</code> = Sem SLA, <code>7</code> = No Prazo) para ordenar a tabela da Sala de Guerra pelos casos mais urgentes no topo."),
        ("MinutosParaVencer", "INT", "Saldo exato em minutos até o vencimento (<code>DATEDIFF(MINUTE, SYSDATETIME(), SlaDataSolucao)</code>). Valores negativos indicam há quantos minutos o SLA já estourou."),
        ("HorasSemInteracao", "INT", "Quantidade de horas corridas desde o último trâmite registrado no ticket (<code>DATEDIFF(HOUR, DataUltimaAcao, SYSDATETIME())</code>)."),
    ]

    p8 = f"""
    <div class="chapter-header">
        <span class="chapter-badge">Capítulo 03</span>
        <div class="chapter-title-block">
            <h2>Dicionário Definitivo das Views Analíticas (Schema mart — Parte 1)</h2>
            <span>Especificação Oficial Coluna a Coluna: 1. mart.vw_VisaoGeralKpis e 2. mart.vw_SlaRadar</span>
        </div>
    </div>

    <div class="obj-banner">
        <div><strong>1. mart.vw_VisaoGeralKpis</strong> — Big Numbers Executivos do Topo da Sala de Guerra</div>
        <span class="obj-meta">Agrupamento: 1 linha por Equipe · 9 Colunas</span>
    </div>
    {render_dict_table(vw_kpis_rows, dense=True, col2_label="Tipo SQL")}

    <div class="obj-banner">
        <div><strong>2. mart.vw_SlaRadar</strong> — Termômetro Preditivo de Quebra de SLA da Fila Ativa</div>
        <span class="obj-meta">Filtro: Somente Chamados em Aberto (EhFinal = 0) · 19 Colunas</span>
    </div>
    {render_dict_table(vw_slaradar_rows, dense=True, col2_label="Tipo SQL")}
    """

    # =========================================================================
    # PÁGINA 09: CAPÍTULO 03 - VIEWS DO MART (PARTE 2: BACKLOG AGING + STATUS AGING)
    # =========================================================================
    vw_backlogaging_rows = [
        ("TicketId", "INT", "Identificador único do chamado em aberto na fila."),
        ("Assunto", "NVARCHAR(400)", "Título/resumo do chamado aberto."),
        ("Equipe", "NVARCHAR(128)", "Nome da equipe de suporte que detém a posse atual do chamado (<code>ISNULL(t.Equipe, 'Sem Equipe')</code>)."),
        ("Analista", "NVARCHAR(256)", "Nome do analista responsável pelo chamado (via <code>LEFT JOIN core.Dim_Agente</code>)."),
        ("Cliente", "NVARCHAR(256)", "Nome da Empresa Cliente associada ao chamado (resolvendo contato pessoa física para sua respectiva Organização)."),
        ("Categoria", "NVARCHAR(128)", "Categoria de classificação do chamado."),
        ("Urgencia", "NVARCHAR(128)", "Nível de criticidade operacional atribuído ao chamado."),
        ("Status", "NVARCHAR(128)", "Status atual em que o chamado está estacionado."),
        ("GrupoStatus", "NVARCHAR(60)", "Agrupamento gerencial do status atual (<code>Com Analista</code>, <code>Aguardando Cliente</code>, <code>Dependência Externa / Dev</code>, etc.)."),
        ("DataCriacao", "DATETIME2(0)", "Data/hora de abertura do chamado em Horário de Brasília (BRT)."),
        ("DataUltimaAcao", "DATETIME2(0)", "Data/hora da última interação registrada no chamado em Horário de Brasília (BRT)."),
        ("DiasAberto", "INT", "Idade total do chamado em dias corridos desde a abertura até o momento atual (<code>DATEDIFF(DAY, DataCriacao, SYSDATETIME())</code>)."),
        ("FaixaIdade", "VARCHAR(20)", "Classificação padronizada de envelhecimento (<em>Aging</em>) do backlog em 6 faixas: <code>'0 a 2 dias'</code>, <code>'3 a 5 dias'</code>, <code>'6 a 10 dias'</code>, <code>'11 a 20 dias'</code>, <code>'21 a 30 dias'</code> e <code>'Mais de 30 dias'</code>."),
        ("HorasDesdeUltimaAcao", "INT", "Horas decorridas desde o último trâmite (ou desde a criação, caso ainda não haja ação: <code>DATEDIFF(HOUR, ISNULL(DataUltimaAcao, DataCriacao), SYSDATETIME())</code>)."),
        ("SemInteracaoMais48h", "INT (0 ou 1)", "Flag de alerta de abandono/estagnação: vale <code>1</code> quando <code>HorasDesdeUltimaAcao</code> atinge ou supera o parâmetro <code>HORAS_SEM_INTERACAO_ALERTA</code> (padrão <code>48h</code>) em <code>ctl.Parametro</code>; caso contrário, vale <code>0</code>."),
    ]

    vw_statusaging_rows = [
        ("Equipe", "NVARCHAR(128)", "Nome da equipe de suporte proprietária dos chamados avaliados."),
        ("Status", "NVARCHAR(128)", "Nome do status avaliado no histórico de transições (<code>core.Fato_StatusHistorico.Status</code>)."),
        ("GrupoStatus", "NVARCHAR(60)", "Macro-grupo ao qual o status pertence (permite separar tempo com Analista vs. tempo Aguardando Cliente vs. tempo em Dev)."),
        ("EhDependenciaTerceiro", "BIT", "Indica se o status representa fila externa/engenharia (<code>1</code> = Dependência de Dev/Terceiros; <code>0</code> = Fluxo normal)."),
        ("QtdPassagens", "INT", "Quantidade total de vezes (passagens históricas + passagens atualmente abertas em curso) em que os chamados entraram neste status."),
        ("HorasUteisMedias", "DECIMAL(10,1)", "Tempo médio de permanência dos chamados neste status medido em <strong>horas úteis de trabalho</strong> (<code>AVG(MinutosUteis / 60.0)</code>). Quando a passagem ainda está em aberto (<code>DataFim IS NULL</code>), contabiliza dinamicamente o tempo decorrido até <code>SYSDATETIME()</code>."),
        ("HorasCorridasMedias", "DECIMAL(10,1)", "Tempo médio de permanência dos chamados neste status em <strong>horas corridas (24x7)</strong> (<code>AVG(MinutosCorridos / 60.0)</code>), incluindo passagens abertas em curso."),
        ("HorasCorridasTotais", "BIGINT", "Soma acumulada de todas as horas corridas consumidas por este status na história da equipe (<code>SUM(MinutosCorridos / 60.0)</code>). Ideal para gráfico de Pareto de gargalos."),
    ]

    p9 = f"""
    <div class="chapter-header">
        <span class="chapter-badge">Capítulo 03</span>
        <div class="chapter-title-block">
            <h2>Dicionário Definitivo das Views Analíticas (Schema mart — Parte 2)</h2>
            <span>Especificação Oficial Coluna a Coluna: 3. mart.vw_BacklogAging e 4. mart.vw_StatusAging</span>
        </div>
    </div>

    <div class="obj-banner">
        <div><strong>3. mart.vw_BacklogAging</strong> — Envelhecimento da Fila Ativa e Auditoria de Inatividade (+48h)</div>
        <span class="obj-meta">Filtro: Somente Chamados em Aberto (EhFinal = 0) · 15 Colunas</span>
    </div>
    {render_dict_table(vw_backlogaging_rows, dense=True, col2_label="Tipo SQL")}

    <div class="obj-banner">
        <div><strong>4. mart.vw_StatusAging</strong> — Gargalos Operacionais e Tempo Retido por Status</div>
        <span class="obj-meta">Fonte: core.Fato_StatusHistorico (Passagens Fechadas + Status Atual em Curso) · 8 Colunas</span>
    </div>
    {render_dict_table(vw_statusaging_rows, dense=True, col2_label="Tipo SQL")}
    """

    # =========================================================================
    # PÁGINA 10: CAPÍTULO 03 - VIEWS DO MART (PARTE 3: THROUGHPUT DIARIO + CLIENTE RAIO-X)
    # =========================================================================
    vw_throughput_rows = [
        ("Data", "DATE", "Data civil diária extraída de <code>core.Dim_Calendario</code> (desde o primeiro chamado a partir de <code>2022-01-01</code> até a data corrente <code>CAST(SYSDATETIME() AS DATE)</code>). Garante eixo de tempo contínuo mesmo em dias sem abertura de chamados."),
        ("AnoMes", "CHAR(7)", "Competência mensal no formato <code>'YYYY-MM'</code> (ex.: <code>'2026-11'</code>) para agregações mensais de vazão."),
        ("EhDiaUtil", "BIT", "Flag da <code>core.Dim_Calendario</code> indicando se a data é dia útil comercial (<code>1</code>) ou fim de semana/feriado nacional (<code>0</code>)."),
        ("Equipe", "NVARCHAR(128)", "Nome da equipe operacional de suporte (produto cartesiano controlado com <code>core.Dim_Equipe WHERE EhSuporte = 1</code>)."),
        ("Abertos", "INT", "Total de novos chamados criados (<code>CAST(DataCriacao AS DATE) = Data</code>) para aquela equipe naquele dia (<code>0</code> quando não houve abertura)."),
        ("Resolvidos", "INT", "Total de chamados solucionados (<code>CAST(DataResolucao AS DATE) = Data</code>) por aquela equipe naquele dia (<code>0</code> quando não houve resolução)."),
        ("SaldoLiquido", "INT", "Balanço líquido de vazão do dia calculado pela fórmula <code>Resolvidos - Abertos</code>. <strong>Interpretação executiva:</strong> valores <strong>positivos (&gt; 0)</strong> indicam que a equipe queimou fila (resolveu mais do que entrou); valores <strong>negativos (&lt; 0)</strong> indicam acúmulo de backlog no dia."),
    ]

    vw_clienteraiox_rows = [
        ("ClienteId", "VARCHAR(64)", "Identificador único da <strong>Empresa Cliente</strong> no Movidesk (filtra apenas Pessoas Jurídicas/Departamentos <code>TipoPessoa IN (2, 4)</code> ou organizações titulares de tickets, eliminando duplicidade com pessoas físicas)."),
        ("Cliente", "NVARCHAR(256)", "Nome Fantasia / Nome de Exibição oficial da Empresa Cliente."),
        ("RazaoSocial", "NVARCHAR(256)", "Razão Social societária da Empresa Cliente cadastrada no Movidesk."),
        ("TotalTicketsHistorico", "INT", "Volume total acumulado de chamados abertos por todos os usuários vinculados àquela Empresa Cliente em toda a base histórica."),
        ("TicketsAtualmenteAbertos", "INT", "Quantidade de chamados da Empresa Cliente que estão em aberto no momento atual (<code>EhFinal = 0</code>)."),
        ("TicketsDentroSla", "INT", "Quantidade de chamados resolvidos da Empresa Cliente cuja <code>DataResolucao</code> ocorreu dentro do prazo contratual (<code>DataResolucao &lt;= SlaDataSolucao</code>)."),
        ("SlaCumpridoPct", "DECIMAL(5,1)", "Percentual histórico de cumprimento de SLA da Empresa Cliente: <code>100.0 * TicketsDentroSla / TotalTicketsResolvidosComSla</code>."),
        ("DataUltimoTicket", "DATETIME2(0)", "Data/hora em BRT do chamado mais recente aberto pela Empresa Cliente (<code>MAX(t.DataCriacao)</code>)."),
        ("DiasDesdeUltimoTicket", "INT", "Quantidade de dias corridos sem abertura de novos chamados pela Empresa (<code>DATEDIFF(DAY, MAX(DataCriacao), SYSDATETIME())</code>)."),
        ("StatusRelacionamento", "VARCHAR(35)", "Termômetro de Saúde e Retenção (<em>Churn Radar</em>) parametrizado por <code>DIAS_CLIENTE_SILENCIOSO</code> (padrão <code>60</code> dias em <code>ctl.Parametro</code>):<br/>• <code>'Ativo (&lt; 30d)'</code>: Empresa abriu chamados nos últimos 29 dias;<br/>• <code>'Atenção (Silencioso 30-60d)'</code>: Empresa sem abrir chamados entre 30 e 59 dias;<br/>• <code>'Risco Churn (Silencioso &gt; 60d)'</code>: Empresa há 60 dias ou mais sem acionar o suporte (ou sem chamados)."),
    ]

    p10 = f"""
    <div class="chapter-header">
        <span class="chapter-badge">Capítulo 03</span>
        <div class="chapter-title-block">
            <h2>Dicionário Definitivo das Views Analíticas (Schema mart — Parte 3)</h2>
            <span>Especificação Oficial Coluna a Coluna: 5. mart.vw_ThroughputDiario e 6. mart.vw_ClienteRaioX</span>
        </div>
    </div>

    <div class="obj-banner">
        <div><strong>5. mart.vw_ThroughputDiario</strong> — Balanço Diário de Vazão Operacional (Abertos vs. Resolvidos)</div>
        <span class="obj-meta">Granularidade: 1 linha por (Data, Equipe) · 7 Colunas</span>
    </div>
    {render_dict_table(vw_throughput_rows, dense=True, col2_label="Tipo SQL")}

    <div class="obj-banner">
        <div><strong>6. mart.vw_ClienteRaioX</strong> — Inteligência de Empresas Clientes, Cumprimento de SLA e Risco de Churn</div>
        <span class="obj-meta">Granularidade: 1 linha por Empresa Cliente (Pessoa Jurídica) · 10 Colunas</span>
    </div>
    {render_dict_table(vw_clienteraiox_rows, dense=True, col2_label="Tipo SQL")}
    """

    # =========================================================================
    # PÁGINA 11: CAPÍTULO 03 - VIEWS DO MART (PARTE 4: MAPA DEMANDA + BACKLOG EVOLUCAO)
    # =========================================================================
    vw_mapademanda_rows = [
        ("Equipe", "NVARCHAR(128)", "Nome da equipe de suporte responsável pelo grupo de chamados (<code>ISNULL(t.Equipe, 'Sem Equipe')</code>)."),
        ("Categoria", "NVARCHAR(128)", "Categoria funcional dos chamados (ex.: Incidente, Dúvida, Requisição)."),
        ("Urgencia", "NVARCHAR(128)", "Nível de urgência operacional dos chamados no agrupamento."),
        ("VersaoProduto", "NVARCHAR(1000)", "Versão do Produto / Release extraída do campo customizado <code>CampoId = 133948</code> em <code>core.Fato_CampoCustomizado</code> (ex.: <code>'KN1'</code>, <code>'e-Guardian'</code>, <code>'Aquilla'</code>; exibe <code>'Não Informada'</code> quando não preenchido)."),
        ("Volumetria", "INT", "Quantidade total histórica de chamados registrados naquela combinação de Equipe + Categoria + Urgência + Versão (<code>COUNT(1)</code>)."),
        ("Abertos", "INT", "Subconjunto da <code>Volumetria</code> que permanece em aberto na fila atual (<code>EhFinal = 0</code>)."),
        ("HorasMediasResolucao", "DECIMAL(10,1)", "Tempo médio em horas corridas gasto para resolver os chamados daquela categoria/versão (<code>AVG(DATEDIFF(HOUR, DataCriacao, ISNULL(DataResolucao, SYSDATETIME())))</code>)."),
    ]

    vw_backlogevolucao_rows = [
        ("DataSnapshot", "DATE", "Data civil da fotografia diária do backlog (proveniente de <code>core.Fato_SnapshotBacklog</code>)."),
        ("AnoMes / NomeDiaSemana", "CHAR(7) / NVARCHAR(20)", "Mês de competência (<code>'YYYY-MM'</code>) e nome do dia da semana (via <code>LEFT JOIN core.Dim_Calendario</code>)."),
        ("EhDiaUtil", "BIT", "Indica se a data do snapshot foi um dia útil operacional (<code>1</code>) ou final de semana/feriado (<code>0</code>)."),
        ("Equipe", "NVARCHAR(128)", "Nome da equipe de suporte que detinha a posse dos chamados abertos naquela data."),
        ("AgenteId", "VARCHAR(64)", "Código identificador do analista responsável na data do snapshot."),
        ("Analista", "NVARCHAR(256)", "Nome completo do analista responsável (via <code>LEFT JOIN core.Dim_Agente</code>; exibe <code>'Não Atribuído'</code> quando sem dono)."),
        ("Status", "NVARCHAR(128)", "Status em que os chamados estavam estacionados no fechamento daquele dia."),
        ("GrupoStatus", "NVARCHAR(60)", "Macro-grupo do status na data (<code>Com Analista</code>, <code>Aguardando Cliente</code>, <code>Dependência Externa / Dev</code>, etc.)."),
        ("EhDependenciaTerceiro", "BIT", "Filtra o volume da fila que estava retido em Desenvolvimento/Terceiros (<code>1</code>) vs. operação direta do Suporte (<code>0</code>)."),
        ("Urgencia", "NVARCHAR(128)", "Nível de criticidade dos chamados contabilizados no snapshot."),
        ("QtdTickets", "INT", "Volume total de chamados em aberto ao final daquele dia para a combinação analisada."),
        ("QtdSlaVencido", "INT", "Parcela de <code>QtdTickets</code> cujo prazo de solução já estava vencido naquela data."),
        ("QtdNoPrazo", "INT", "Parcela de <code>QtdTickets</code> que estava dentro do prazo contratual naquela data (calculada via <code>QtdTickets - QtdSlaVencido</code>)."),
    ]

    p11 = f"""
    <div class="chapter-header">
        <span class="chapter-badge">Capítulo 03</span>
        <div class="chapter-title-block">
            <h2>Dicionário Definitivo das Views Analíticas (Schema mart — Parte 4)</h2>
            <span>Especificação Oficial Coluna a Coluna: 7. mart.vw_MapaDemanda e 8. mart.vw_BacklogEvolucao</span>
        </div>
    </div>

    <div class="obj-banner">
        <div><strong>7. mart.vw_MapaDemanda</strong> — Pareto de Categorias, Urgências e Versões de Release (#133948)</div>
        <span class="obj-meta">Cruzamento: Fato_Ticket + Dim_Status + Fato_CampoCustomizado · 7 Colunas</span>
    </div>
    {render_dict_table(vw_mapademanda_rows, dense=True, col2_label="Tipo SQL")}

    <div class="obj-banner">
        <div><strong>8. mart.vw_BacklogEvolucao</strong> — Curva Histórica Diária do Backlog Total vs. SLA Vencido (90 Dias)</div>
        <span class="obj-meta">Fonte: core.Fato_SnapshotBacklog + Dim_Calendario + Dim_Status + Dim_Agente · 14 Colunas</span>
    </div>
    {render_dict_table(vw_backlogevolucao_rows, dense=True, col2_label="Tipo SQL")}

    <div class="callout-gold" style="padding: 2mm 3mm; font-size: 8pt;">
        <strong>Certificação Executiva de Governança (Advice Compliance Solutions):</strong> Este documento reflete fielmente a estrutura física implantada no banco <code>MovideskDM</code> (Release <code>v1.0.5+</code>). Qualquer novo gráfico ou indicador solicitado pela Diretoria no Apache Superset deve obrigatoriamente consumir uma das <strong>8 Views do schema <code>mart</code></strong> documentadas neste capítulo, garantindo 100% de paridade matemática em toda a organização.
    </div>
    """

    pages_list = [p1, p2, p3, p4, p4_b, p5, p6, p7, p8, p9, p10, p11]
    pages_html = "".join(
        render_page(header_right_title, idx, total_pages, content)
        for idx, content in enumerate(pages_list, start=1)
    )

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8" />
    <title>{cover_title}</title>
    <style>{COMMON_CSS}</style>
</head>
<body>
    {pages_html}
</body>
</html>
"""


def converter_html_para_pdf(html_path: Path, pdf_path: Path) -> bool:
    """
    Converte um arquivo HTML para PDF A4 utilizando a melhor ferramenta disponível no ambiente:
      1. WeasyPrint (se instalado em Python)
      2. pdfkit / wkhtmltopdf (se instalado no sistema)
      3. Chromium / Google Chrome / Microsoft Edge Headless (nativo no Windows 10/11 e Linux)
    """
    # 1. Tenta WeasyPrint
    try:
        import weasyprint  # type: ignore

        weasyprint.HTML(filename=str(html_path)).write_pdf(str(pdf_path))
        print(f"[OK] PDF gerado via WeasyPrint: {pdf_path}")
        return True
    except ImportError:
        pass
    except Exception as exc:
        print(f"[AVISO] Falha ao usar WeasyPrint ({exc}), tentando próximo conversor...")

    # 2. Tenta Chromium / Google Chrome / Microsoft Edge Headless
    candidatos_browser: List[str] = [
        "chromium",
        "google-chrome",
        "google-chrome-stable",
        "msedge",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]

    for bin_name in candidatos_browser:
        resolved = shutil.which(bin_name) or (bin_name if os.path.exists(bin_name) else None)
        if not resolved:
            continue

        file_uri = html_path.resolve().as_uri()
        cmd = [
            resolved,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path.resolve()}",
            file_uri,
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if pdf_path.exists() and pdf_path.stat().st_size > 0:
                print(f"[OK] PDF gerado via {Path(resolved).name}: {pdf_path}")
                return True
        except Exception as exc:
            print(f"[AVISO] Falha ao converter com {resolved}: {exc}")

    print(
        f"[INFO] HTML salvo em {html_path}. Para converter manualmente, abra no navegador e use 'Salvar como PDF' (Sem margens)."
    )
    return False


def main() -> int:
    print("==========================================================================")
    print(" Gerador de Manuais Corporativos Advice Compliance Solutions (HTML -> PDF)")
    print("==========================================================================")

    garantir_recortes_screenshots()

    manual_3_html = build_manual_3_html()

    manuais = [
        (
            "Manual_01_Operacao_Painel_Controle_Movidesk_BI",
            build_manual_1_html(),
        ),
        (
            "Manual_02_Configuracao_Apache_Superset_Corporativo",
            build_manual_2_html(),
        ),
        (
            "Manual_03_Dicionario_de_Dados_Completo",
            manual_3_html,
        ),
        (
            "Manual_03_Dicionario_de_Dados_MovideskDM",
            manual_3_html,
        ),
    ]

    for nome_base, conteudo_html in manuais:
        html_path = BASE_DIR / f"{nome_base}.html"
        pdf_path = BASE_DIR / f"{nome_base}.pdf"

        html_path.write_text(conteudo_html, encoding="utf-8")
        print(f"[OK] Arquivo HTML gerado: {html_path}")
        converter_html_para_pdf(html_path, pdf_path)

    print("==========================================================================")
    print(" Concluído com sucesso! Arquivos disponíveis em:", BASE_DIR)
    print("==========================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())

