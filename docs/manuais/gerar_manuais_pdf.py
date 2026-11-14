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


def build_manual_3_html() -> str:
    """Constrói o HTML completo do Manual 3: Dicionário de Dados MovideskDM."""
    header_right_title = "MANUAL DE ARQUITETURA - Dicionário de Dados"
    cover_title = "MANUAL DE ARQUITETURA - Dicionário de Dados (MovideskDM)"
    total_pages = 4

    img_ssms = img_to_data_uri("ssms_arvore_movideskdm.png")

    # -------------------------------------------------------------------------
    # PÁGINA 1: CAPA + 3 DESTAQUES + ÍNDICE + SCREENSHOT SSMS
    # -------------------------------------------------------------------------
    p1 = f"""
    <div class="cover-banner">
        <span class="cover-tag">Engenharia de Dados &amp; Business Intelligence · Data Mart Oficial</span>
        <h1>{cover_title}</h1>
        <p>Guia de modelagem de dados, arquitetura em camadas (Schemas) e catálogo de Views para o Superset. Documento de referência técnica concebido para orientar analistas de BI e engenheiros na leitura correta da base MovideskDM.</p>
        <div class="cover-meta-strip">
            <span><strong>Banco de Dados:</strong> Microsoft SQL Server (MovideskDM)</span>
            <span><strong>Arquitetura:</strong> Medallion + Star Schema</span>
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
                <h3>Arquitetura em Camadas (Medallion)</h3>
                <p>Isolamento rigoroso entre pouso bruto JSON (<code>raw</code>), modelo estrela limpo (<code>core</code>), auditoria/segurança (<code>ctl</code>/<code>sec</code>) e consumo (<code>mart</code>).</p>
            </div>
        </div>
        <div class="highlight-card">
            <div class="highlight-num">02</div>
            <div class="highlight-content">
                <h3>Modelagem Estrela (Fatos &amp; Dimensões)</h3>
                <p>Separação clara entre o contexto descritivo — <em>Quem, Quando, Onde, Como</em> (<code>Dim_*</code>) — e os eventos e métricas mensuráveis de SLA (<code>Fato_*</code>).</p>
            </div>
        </div>
        <div class="highlight-card">
            <div class="highlight-num">03</div>
            <div class="highlight-content">
                <h3>Camada Semântica Pronta (Schema mart)</h3>
                <p>Catálogo de Views analíticas que encapsulam <code>JOINs</code>, conversão para Horário de Brasília e vínculo Empresa vs. Pessoa Física para o Superset.</p>
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
                    <span class="toc-title">A Arquitetura em Camadas (Schemas)</span>
                    <span class="toc-desc">— Por que não misturar dados: pipeline Medallion (raw, core, ctl, sec e mart)</span>
                </div>
                <span class="toc-page">Página 02</span>
            </li>
            <li class="toc-item">
                <div class="toc-item-left">
                    <span class="toc-badge">CAPÍTULO 02</span>
                    <span class="toc-title">Lendo as Tabelas de Ingestão (raw) e Negócio (core)</span>
                    <span class="toc-desc">— Como cruzar Dimensões (Quem/Quando/Onde) e Fatos (Eventos/Números)</span>
                </div>
                <span class="toc-page">Página 03</span>
            </li>
            <li class="toc-item">
                <div class="toc-item-left">
                    <span class="toc-badge">CAPÍTULO 03</span>
                    <span class="toc-title">A Camada Semântica (As Views do Schema mart)</span>
                    <span class="toc-desc">— Catálogo oficial de Views analíticas certificadas para o Apache Superset</span>
                </div>
                <span class="toc-page">Página 04</span>
            </li>
        </ul>
    </div>

    <div class="screenshot-placeholder-box">
        <div class="screenshot-placeholder-tag">[INSERIR IMAGEM AQUI: Screenshot do SSMS com a árvore do banco MovideskDM]</div>
        {f'<div class="screenshot-img-wrapper"><img src="{img_ssms}" style="max-height: 55mm;" alt="Árvore do banco MovideskDM no SSMS" /></div>' if img_ssms else ''}
        <div class="screenshot-caption">Figura 0.1 — Árvore real do banco MovideskDM no SQL Server Management Studio (SSMS) exibindo as Tabelas (core, ctl, raw, sec) e Exibições (mart.vw_*).</div>
    </div>
    """

    # -------------------------------------------------------------------------
    # PÁGINA 2: CAPÍTULO 01 - A ARQUITETURA EM CAMADAS (SCHEMAS)
    # -------------------------------------------------------------------------
    p2 = """
    <div class="chapter-header">
        <span class="chapter-badge">Capítulo 01</span>
        <div class="chapter-title-block">
            <h2>A Arquitetura em Camadas (Schemas — Medallion Architecture)</h2>
            <span>Por que o Banco MovideskDM Não Guarda Tudo "Junto e Misturado" em um Único Schema</span>
        </div>
    </div>

    <p class="lead-text">
        Um erro clássico em projetos de BI é jogar o retorno da API diretamente nas mesmas tabelas que os relatórios consultam. Quando a API muda um campo, traz duplicidades ou envia datas em fuso horário universal (<code>UTC</code>), todos os painéis quebram ou exibem números incorretos. Para blindar a operação da Advice, o banco <strong>MovideskDM</strong> adota a <strong>Arquitetura Medalhão (Medallion Architecture)</strong> dividida em 5 schemas especializados:
    </p>

    <div class="steps-container">
        <div class="step-row">
            <div class="step-circle">1</div>
            <div class="step-text">
                <strong>Schema <code>raw</code> (Camada Bronze — Área de Pouso Bruta):</strong> Recebe os dados da API do Movidesk exatamente como vêm do JSON original (coluna <code>Payload NVARCHAR(MAX)</code>). Não fazemos filtros nem cálculos aqui. A grande vantagem: se precisarmos criar uma regra nova de negócio amanhã, reprocessamos os 46.850+ chamados direto do <code>raw</code> em segundos, sem precisar baixar tudo de novo da internet!
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">2</div>
            <div class="step-text">
                <strong>Schema <code>core</code> (Camada Prata — O "Coração" em Modelo Estrela):</strong> Alimentado pelas procedures <code>core.usp_ProcessarTickets</code> e <code>core.usp_ProcessarPessoas</code>. Aqui o JSON bruto é desmontado, limpo, tipado (<code>INT</code>, <code>DATETIME2</code>, <code>BIT</code>), convertido de <strong>UTC para Horário de Brasília (BRT)</strong> e organizado em <strong>Fatos e Dimensões</strong> para leitura relacional ultrarrápida.
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">3</div>
            <div class="step-text">
                <strong>Schemas <code>ctl</code> e <code>sec</code> (Governança, Controle e Segurança):</strong> O schema <code>ctl</code> é o "painel de instrumentos" do motor de carga: guarda o histórico de execuções (<code>ctl.ExecucaoCarga</code>), parâmetros de negócio (<code>ctl.Parametro</code>) e a <strong>"marca d'água"</strong> (<code>ctl.MarcaDagua</code>) que diz ao extrator de qual minuto exato continuar. Já o schema <code>sec</code> controla quem pode ver quais equipes no Superset (<em>Row Level Security</em>).
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">4</div>
            <div class="step-text">
                <strong>Schema <code>mart</code> (Camada Ouro — Consumo Analítico / BI):</strong> É a vitrine pronta para consumo. Esconde toda a complexidade de <code>JOINs</code>, regras de SLA e tratamento de nulos dentro de <strong>Views certificadas</strong> (<code>mart.vw_*</code>). É exclusivamente daqui que o Apache Superset lê os dados.
            </div>
        </div>
    </div>

    <table class="zebra-table">
        <thead>
            <tr>
                <th style="width: 15%;">Schema SQL</th>
                <th style="width: 19%;">Camada Medalhão</th>
                <th style="width: 28%;">Principais Objetos</th>
                <th>Papel na Engenharia e Quem Deve Acessar</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><span class="badge-pill badge-gold">raw</span></td>
                <td><strong>Bronze (Pouso)</strong></td>
                <td><code>raw.Ticket</code>, <code>raw.Pessoa</code></td>
                <td>Guarda o JSON intacto da API e a flag <code>Processado (0/1)</code>. <em>Acesso: exclusivo do Extrator C# e procedures de carga.</em></td>
            </tr>
            <tr>
                <td><span class="badge-pill badge-teal">core</span></td>
                <td><strong>Prata (Coração)</strong></td>
                <td><code>core.Dim_*</code> (6 tabelas)<br/><code>core.Fato_*</code> (8 tabelas)</td>
                <td>Modelo Estrela normalizado em Horário de Brasília (BRT) com chaves indexadas. <em>Acesso: Engenheiros de Dados e Views do mart.</em></td>
            </tr>
            <tr>
                <td><span class="badge-pill badge-teal">ctl</span></td>
                <td><strong>Controle ETL</strong></td>
                <td><code>ctl.MarcaDagua</code>, <code>ctl.Parametro</code>, <code>ctl.ExecucaoCarga</code></td>
                <td>Orquestra cursores de retomada, limiares de alerta (4h, 48h, 60d) e logs de auditoria. <em>Acesso: Painel de Controle e DBAs.</em></td>
            </tr>
            <tr>
                <td><span class="badge-pill badge-teal">sec</span></td>
                <td><strong>Segurança (RLS)</strong></td>
                <td><code>sec.UsuarioEquipe</code></td>
                <td>Mapeia qual login do Superset tem permissão para visualizar cada Equipe de suporte. <em>Acesso: Administradores de BI.</em></td>
            </tr>
            <tr>
                <td><span class="badge-pill badge-green">mart</span></td>
                <td><strong>Ouro (Consumo)</strong></td>
                <td><code>mart.vw_*</code> (8 Views Analíticas)</td>
                <td>Camada Semântica pronta para gráficos e relatórios. <strong><em>Acesso: Apache Superset e Analistas de BI.</em></strong></td>
            </tr>
        </tbody>
    </table>

    <div class="callout-gold">
        <strong>Visão do Arquiteto (Fluxo do Dado de Ponta a Ponta):</strong><br/>
        <code>API Movidesk (JSON UTC)</code> ──► <code>raw.Ticket / raw.Pessoa</code> ──► <code>core.usp_ProcessarTickets (Normaliza + Converte BRT)</code> ──► <code>core.Dim_* + core.Fato_*</code> ──► <code>mart.vw_* (Views Analíticas)</code> ──► <code>Apache Superset (Dashboards)</code>
    </div>
    """

    # -------------------------------------------------------------------------
    # PÁGINA 3: CAPÍTULO 02 - LENDO AS TABELAS DE INGESTÃO (RAW) E NEGÓCIO (CORE)
    # -------------------------------------------------------------------------
    p3 = """
    <div class="chapter-header">
        <span class="chapter-badge">Capítulo 02</span>
        <div class="chapter-title-block">
            <h2>Lendo as Tabelas de Ingestão (raw) e Negócio (core)</h2>
            <span>Guia Prático do Modelo Estrela: Como Entender e Cruzar Ingestão, Dimensões e Fatos</span>
        </div>
    </div>

    <p class="lead-text">
        Para navegar com segurança pelo banco <strong>MovideskDM</strong>, todo analista de BI precisa dominar a divisão clássica de um <em>Data Warehouse</em> entre <strong>Ingestão Bruta</strong>, <strong>Dimensões</strong> e <strong>Tabelas Fato</strong>:
    </p>

    <div class="steps-container compact">
        <div class="step-row">
            <div class="step-circle">1</div>
            <div class="step-text">
                <strong>A Ingestão Bruta (<code>raw.Ticket</code> e <code>raw.Pessoa</code>):</strong> É onde tudo começa. Os dados chegam "sujos" em um grande texto JSON dentro da coluna <code>Payload</code>. Você nunca faz cálculos direto nelas; elas existem para alimentar o <code>core</code> quando <code>Processado = 0</code>.
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">2</div>
            <div class="step-text">
                <strong>As Dimensões (<code>core.Dim_*</code> — O "QUEM, QUANDO, ONDE e COMO"):</strong> Guardam os cadastros e características descritivas (textos, nomes, classificações). <em>Exemplo prático:</em> Na tabela de chamados temos apenas o código <code>EmpresaId</code>; se quero exibir o <strong>Nome Fantasia</strong> ou a <strong>Razão Social</strong> do cliente, busco na <code>core.Dim_Cliente</code>. Se quero saber se o status <em>"Aguardando Versão"</em> é dependência de desenvolvimento ou se já encerrou o chamado (<code>EhFinal = 1</code>), busco na <code>core.Dim_Status</code>.
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">3</div>
            <div class="step-text">
                <strong>Os Fatos (<code>core.Fato_*</code> — Os "EVENTOS e NÚMEROS"):</strong> Guardam os acontecimentos operacionais, datas, tempos e quantidades. A tabela central <code>core.Fato_Ticket</code> registra cada chamado, seus prazos de SLA, datas de abertura/resolução e faz a ponte (<code>JOIN</code>) com as Dimensões através dos IDs.
            </div>
        </div>
    </div>

    <table class="zebra-table compact">
        <thead>
            <tr>
                <th style="width: 24%;">Tabela no Banco</th>
                <th style="width: 14%;">Papel</th>
                <th style="width: 23%;">Chave Primária / JOIN</th>
                <th>O Que Ela Guarda e Como Ler / Cruzar</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><code>raw.Ticket</code><br/><code>raw.Pessoa</code></td>
                <td><span class="badge-pill badge-gold">Ingestão</span></td>
                <td><code>TicketId</code> (INT)<br/><code>PessoaId</code> (VARCHAR)</td>
                <td>Guarda o JSON bruto (<code>Payload</code>), data de atualização UTC (<code>LastUpdateUtc</code>) e flag <code>Processado</code>. Origem de todos os dados do <code>core</code>.</td>
            </tr>
            <tr>
                <td><code>core.Dim_Cliente</code></td>
                <td><span class="badge-pill badge-teal">Dimensão</span></td>
                <td><code>ClienteId</code><br/>(Auto-join: <code>EmpresaId</code>)</td>
                <td><strong>QUEM (Cliente/Empresa):</strong> Nome, Razão Social e <code>TipoPessoa</code> (<code>2</code> = Empresa, <code>1</code> = Contato). Contatos apontam para sua empresa via <code>EmpresaId</code>.</td>
            </tr>
            <tr>
                <td><code>core.Dim_Agente</code><br/><code>core.Dim_Equipe</code></td>
                <td><span class="badge-pill badge-teal">Dimensão</span></td>
                <td><code>AgenteId</code><br/><code>Nome</code> (Equipe)</td>
                <td><strong>QUEM ATENDE (Analista e Time):</strong> Nome e e-mail do analista responsável (<code>Dim_Agente</code>) e lista oficial de equipes de suporte (<code>Dim_Equipe</code>).</td>
            </tr>
            <tr>
                <td><code>core.Dim_Status</code></td>
                <td><span class="badge-pill badge-teal">Dimensão</span></td>
                <td><code>Nome</code> (Status)</td>
                <td><strong>COMO ESTÁ:</strong> Traduz cada status do Movidesk em <code>GrupoStatus</code>, flag <code>EhFinal (0/1)</code>, <code>PausaSla</code> e <code>EhDependenciaTerceiro</code>.</td>
            </tr>
            <tr>
                <td><code>core.Dim_Calendario</code></td>
                <td><span class="badge-pill badge-teal">Dimensão</span></td>
                <td><code>Data</code> (DATE)</td>
                <td><strong>QUANDO:</strong> Todos os dias de 2022 a 2028 com <code>AnoMes</code>, <code>NomeDiaSemana</code>, <code>EhFimDeSemana</code>, <code>EhFeriado</code> e <code>EhDiaUtil</code>.</td>
            </tr>
            <tr>
                <td><code>core.Dim_CampoCustomizado</code></td>
                <td><span class="badge-pill badge-teal">Dimensão</span></td>
                <td><code>CampoId</code> (INT)</td>
                <td><strong>METADADO EXTRA:</strong> Dicionário dos campos adicionais de formulário (ex.: <code>133948</code> = Versão do Produto / Release).</td>
            </tr>
            <tr>
                <td><code>core.Fato_Ticket</code></td>
                <td><span class="badge-pill badge-green">Fato Central</span></td>
                <td>PK: <code>TicketId</code><br/>FKs: <code>EmpresaId</code>, <code>AgenteId</code>, <code>Status</code>, <code>Equipe</code></td>
                <td><strong>O CHAMADO:</strong> 1 linha por ticket. Guarda Assunto, Urgência, Categoria, Datas em BRT (Criação, Resolução, Fechamento), prazos de SLA (<code>SlaDataSolucao</code>) e FCR.</td>
            </tr>
            <tr>
                <td><code>core.Fato_StatusHistorico</code></td>
                <td><span class="badge-pill badge-green">Fato Evento</span></td>
                <td><code>(TicketId, Sequencia)</code></td>
                <td><strong>ONDE PAROU:</strong> Cada passagem do chamado por um status, com <code>DataInicio</code>, <code>DataFim</code> e minutos úteis/corridos gastos naquela etapa.</td>
            </tr>
            <tr>
                <td><code>core.Fato_SnapshotBacklog</code></td>
                <td><span class="badge-pill badge-green">Fato Foto</span></td>
                <td><code>(DataSnapshot, Equipe, AgenteId, Status, Urgencia)</code></td>
                <td><strong>MEMÓRIA DA FILA:</strong> Fotografia diária de quantos tickets estavam abertos (<code>QtdTickets</code>) e vencidos (<code>QtdSlaVencido</code>) a cada dia dos últimos 90 dias.</td>
            </tr>
            <tr>
                <td><code>core.Fato_Acao</code><br/><code>core.Fato_CampoCustomizado</code></td>
                <td><span class="badge-pill badge-green">Fato Detalhe</span></td>
                <td><code>(TicketId, AcaoId)</code><br/><code>(TicketId, CampoId)</code></td>
                <td>Interações/ações do chamado (<code>Fato_Acao</code>) e valores preenchidos nos campos customizados do ticket, como a Versão de Release (<code>Fato_CampoCustomizado</code>).</td>
            </tr>
        </tbody>
    </table>
    """

    # -------------------------------------------------------------------------
    # PÁGINA 4: CAPÍTULO 03 - A CAMADA SEMÂNTICA (AS VIEWS DO SCHEMA MART)
    # -------------------------------------------------------------------------
    p4 = """
    <div class="chapter-header">
        <span class="chapter-badge">Capítulo 03</span>
        <div class="chapter-title-block">
            <h2>A Camada Semântica (Catálogo de Views do Schema mart)</h2>
            <span>Por que o Apache Superset e os Analistas Devem Ler Exclusivamente as Views do Schema mart</span>
        </div>
    </div>

    <div class="callout-gold" style="padding: 1.8mm 2.8mm; font-size: 8.1pt;">
        <strong>Regra de Ouro da Arquitetura Advice:</strong> O usuário final e o Apache Superset <strong>JAMAIS devem fazer <code>SELECT</code> diretamente nas tabelas <code>raw</code> ou <code>core</code></strong>. Se um analista consultar <code>core.Fato_Ticket</code> direto sem fazer o <code>LEFT JOIN</code> correto com <code>core.Dim_Status</code> ou sem resolver a hierarquia <code>Contato → Empresa</code> em <code>core.Dim_Cliente</code>, o relatório apresentará números divergentes da Sala de Guerra. Use <strong>sempre</strong> as Views do schema <strong><code>mart</code></strong>, onde todas as regras de negócio já estão mastigadas e padronizadas!
    </div>

    <div class="steps-container compact">
        <div class="step-row">
            <div class="step-circle">1</div>
            <div class="step-text">
                <strong>Fila de Hoje e Radar de SLA Iminente (<code>mart.vw_VisaoGeralKpis</code> e <code>mart.vw_SlaRadar</code>):</strong> A <code>vw_VisaoGeralKpis</code> consolida os Big Numbers executivos por Equipe (Backlog Atual, SLA Vencido, SLA Iminente &lt; 4h, Pausados, Dependência Dev, Abertos/Resolvidos Hoje e % FCR). Já a <code>vw_SlaRadar</code> lista cada chamado aberto na fila com seu termômetro preditivo (<code>Vencido</code>, <code>Crítico &lt; 2h</code>, <code>Alerta &lt; 4h</code>, <code>Atenção &lt; 8h</code>) e minutos restantes para vencer.
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">2</div>
            <div class="step-text">
                <strong>Envelhecimento da Fila e Gargalos por Status (<code>mart.vw_BacklogAging</code>, <code>mart.vw_StatusAging</code> e <code>mart.vw_BacklogEvolucao</code>):</strong> A <code>vw_BacklogAging</code> classifica os chamados abertos por faixa de idade (<code>0 a 2 dias</code> até <code>Mais de 30 dias</code>) e destaca tickets esquecidos sem interação há mais de 48h. A <code>vw_StatusAging</code> revela em qual status os chamados passam mais horas paradas (incluindo o tempo em curso do status aberto atual), enquanto a <code>vw_BacklogEvolucao</code> desenha a curva histórica dos últimos 90 dias.
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">3</div>
            <div class="step-text">
                <strong>Balanço Diário de Vazão (<code>mart.vw_ThroughputDiario</code>):</strong> Cruza a <code>core.Dim_Calendario</code> com as datas de abertura e resolução da <code>core.Fato_Ticket</code>, entregando para cada dia e equipe o total de chamados <code>Abertos</code>, <code>Resolvidos</code> e o <code>SaldoLiquido</code> (se a fila cresceu ou diminuiu no dia).
            </div>
        </div>
        <div class="step-row">
            <div class="step-circle">4</div>
            <div class="step-text">
                <strong>Saúde de Empresas Clientes e Pareto de Demanda (<code>mart.vw_ClienteRaioX</code> e <code>mart.vw_MapaDemanda</code>):</strong> A <code>vw_ClienteRaioX</code> agrupa apenas <strong>Empresas Clientes reais</strong> (ignorando pessoas físicas avulsas já vinculadas), calculando % de SLA cumprido e identificando automaticamente <strong>Clientes Silenciosos há mais de 60 dias (Risco de Churn)</strong>. Por fim, a <code>vw_MapaDemanda</code> cruza Categorias e Urgências com a <strong>Versão do Produto/Release</strong> (<code>CampoId = 133948</code>).
            </div>
        </div>
    </div>

    <table class="zebra-table compact">
        <thead>
            <tr>
                <th style="width: 25%;">View Certificada (Schema mart)</th>
                <th style="width: 31%;">Tabelas core Cruzadas Internamente</th>
                <th>Pergunta de Negócio que Ela Responde no Superset</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><code>mart.vw_VisaoGeralKpis</code></td>
                <td><code>Fato_Ticket</code> + <code>Dim_Status</code> + <code>ctl.Parametro</code></td>
                <td><em>"Como está a fotografia instantânea da operação hoje em cada equipe?"</em></td>
            </tr>
            <tr>
                <td><code>mart.vw_SlaRadar</code></td>
                <td><code>Fato_Ticket</code> + <code>Dim_Status</code> + <code>Dim_Agente</code> + <code>Dim_Cliente</code> (Empresa)</td>
                <td><em>"Quais chamados abertos já estouraram ou vão estourar o SLA nas próximas 2h / 4h?"</em></td>
            </tr>
            <tr>
                <td><code>mart.vw_BacklogAging</code></td>
                <td><code>Fato_Ticket</code> + <code>Dim_Status</code> + <code>Dim_Agente</code> + <code>Dim_Cliente</code> (Empresa)</td>
                <td><em>"Há quantos dias cada chamado aberto está na fila e quais estão sem resposta há +48h?"</em></td>
            </tr>
            <tr>
                <td><code>mart.vw_StatusAging</code></td>
                <td><code>Fato_StatusHistorico</code> + <code>Fato_Ticket</code> + <code>Dim_Status</code></td>
                <td><em>"Em qual status do fluxo (Analista, Cliente ou Dev) nossos chamados perdem mais tempo?"</em></td>
            </tr>
            <tr>
                <td><code>mart.vw_BacklogEvolucao</code></td>
                <td><code>Fato_SnapshotBacklog</code> + <code>Dim_Calendario</code> + <code>Dim_Status</code> + <code>Dim_Agente</code></td>
                <td><em>"O nosso backlog total e o volume de SLA vencido estão subindo ou caindo nos últimos 90 dias?"</em></td>
            </tr>
            <tr>
                <td><code>mart.vw_ThroughputDiario</code></td>
                <td><code>Dim_Calendario</code> + <code>Dim_Equipe</code> + <code>Fato_Ticket</code> (Abertos/Resolvidos)</td>
                <td><em>"Estamos resolvendo mais chamados do que entram por dia útil em cada equipe?"</em></td>
            </tr>
            <tr>
                <td><code>mart.vw_ClienteRaioX</code></td>
                <td><code>Dim_Cliente</code> (Empresas) + <code>Fato_Ticket</code> + <code>Dim_Status</code></td>
                <td><em>"Quais Empresas mais demandam suporte, qual o SLA delas e quais pararam de abrir ticket (&gt;60d)?"</em></td>
            </tr>
            <tr>
                <td><code>mart.vw_MapaDemanda</code></td>
                <td><code>Fato_Ticket</code> + <code>Dim_Status</code> + <code>Fato_CampoCustomizado</code> (<code>133948</code>)</td>
                <td><em>"Quais categorias e versões de release (KN1, e-Guardian, etc.) concentram mais incidentes?"</em></td>
            </tr>
        </tbody>
    </table>
    """

    pages_html = (
        render_page(header_right_title, 1, total_pages, p1)
        + render_page(header_right_title, 2, total_pages, p2)
        + render_page(header_right_title, 3, total_pages, p3)
        + render_page(header_right_title, 4, total_pages, p4)
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
            "Manual_03_Dicionario_de_Dados_MovideskDM",
            build_manual_3_html(),
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
