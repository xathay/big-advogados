"""Brazilian electronic judicial systems organized by state/court level."""

from __future__ import annotations

JUDICIAL_STATES = [
    {
        "name": "Tribunais Superiores",
        "subtitle": "STJ · TST · CNJ",
        "icon": "starred-symbolic",
        "systems": [
            {
                "name": "Portal — STJ",
                "url": "https://www.stj.jus.br",
                "description": "Portal do Superior Tribunal de Justiça",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "Consulta Processual — STJ",
                "url": "https://processo.stj.jus.br/processo/pesquisa/",
                "description": "Pesquisa de processos no STJ",
                "icon": "system-search-symbolic",
            },
            {
                "name": "PJe — TST",
                "url": "https://pje.tst.jus.br",
                "description": "PJe — Tribunal Superior do Trabalho",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "Portal PJe — CNJ",
                "url": "https://www.cnj.jus.br/programas-e-acoes/processo-judicial-eletronico-pje/",
                "description": "Portal PJe — Conselho Nacional de Justiça",
                "icon": "document-send-symbolic",
            },
        ],
    },
    {
        "name": "Bahia",
        "subtitle": "TJBA · TRF1 · TRT5",
        "icon": "mark-location-symbolic",
        "systems": [
            {
                "name": "PJe — TJBA 1ª Instância",
                "url": "https://pje.tjba.jus.br",
                "description": "Processo Judicial Eletrônico — Tribunal de Justiça da Bahia",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TJBA 2ª Instância",
                "url": "https://pje2g.tjba.jus.br",
                "description": "PJe 2º Grau — TJBA",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TRF1 1ª Instância",
                "url": "https://pje1g.trf1.jus.br",
                "description": "PJe — Tribunal Regional Federal da 1ª Região",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TRF1 2ª Instância",
                "url": "https://pje2g.trf1.jus.br",
                "description": "PJe 2º Grau — TRF1",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TRT5 (Bahia)",
                "url": "https://pje.trt5.jus.br",
                "description": "PJe — Tribunal Regional do Trabalho 5ª Região",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PROJUDI — TJBA",
                "url": "https://projudi.tjba.jus.br",
                "description": "Processo Judicial Digital — TJBA (sistema legado)",
                "icon": "document-properties-symbolic",
            },
            {
                "name": "Portal — TJBA",
                "url": "https://www.tjba.jus.br",
                "description": "Portal do Tribunal de Justiça da Bahia",
                "icon": "system-search-symbolic",
            },
        ],
    },
    {
        "name": "São Paulo",
        "subtitle": "TJSP · eSAJ",
        "icon": "mark-location-symbolic",
        "systems": [
            {
                "name": "eSAJ — TJSP 1ª Instância",
                "url": "https://esaj.tjsp.jus.br/cpopg/open.do",
                "description": "Consulta Processual 1º Grau — eSAJ / TJSP",
                "icon": "system-search-symbolic",
            },
            {
                "name": "eSAJ — TJSP 2ª Instância",
                "url": "https://esaj.tjsp.jus.br/cposg/open.do",
                "description": "Consulta Processual 2º Grau — eSAJ / TJSP",
                "icon": "system-search-symbolic",
            },
            {
                "name": "Portal eSAJ — TJSP",
                "url": "https://esaj.tjsp.jus.br/esaj/portal.do?servico=190090",
                "description": "Portal de serviços eSAJ — TJSP",
                "icon": "document-send-symbolic",
            },
            {
                "name": "PJe — TRT2 (São Paulo)",
                "url": "https://pje.trt2.jus.br",
                "description": "PJe — Tribunal Regional do Trabalho 2ª Região",
                "icon": "document-edit-symbolic",
            },
        ],
    },
    {
        "name": "Distrito Federal",
        "subtitle": "TJDFT · TRF1 · TRT10",
        "icon": "mark-location-symbolic",
        "systems": [
            {
                "name": "PJe — TJDFT 1ª Instância",
                "url": "https://pje.tjdft.jus.br",
                "description": "PJe — Tribunal de Justiça do Distrito Federal e Territórios",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TJDFT 2ª Instância",
                "url": "https://pje2i.tjdft.jus.br",
                "description": "PJe 2º Grau — TJDFT",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TRT10 (DF/TO)",
                "url": "https://pje.trt10.jus.br",
                "description": "PJe — Tribunal Regional do Trabalho 10ª Região",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "Consulta Processual — TJDFT",
                "url": "https://www.tjdft.jus.br/consultas",
                "description": "Portal de consultas processuais — TJDFT",
                "icon": "system-search-symbolic",
            },
        ],
    },
    {
        "name": "Rio de Janeiro",
        "subtitle": "TJRJ · TRF2 · TRT1",
        "icon": "mark-location-symbolic",
        "systems": [
            {
                "name": "PJe — TJRJ",
                "url": "https://tjrj.pje.jus.br/pje/login.seam",
                "description": "Processo Judicial Eletrônico — Tribunal de Justiça do Rio de Janeiro",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "eProc — TRF2",
                "url": "https://eproc.trf2.jus.br",
                "description": "eProc — Tribunal Regional Federal da 2ª Região",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TRT1 (Rio de Janeiro)",
                "url": "https://pje.trt1.jus.br",
                "description": "PJe — Tribunal Regional do Trabalho 1ª Região",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "Consulta Processual — TJRJ",
                "url": "https://www3.tjrj.jus.br/consultaprocessual/",
                "description": "Consulta de processos — TJRJ",
                "icon": "system-search-symbolic",
            },
        ],
    },
    {
        "name": "Minas Gerais",
        "subtitle": "TJMG · TRF1 · TRT3",
        "icon": "mark-location-symbolic",
        "systems": [
            {
                "name": "PJe — TJMG",
                "url": "https://pje.tjmg.jus.br",
                "description": "PJe — Tribunal de Justiça de Minas Gerais",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TRT3 (Minas Gerais)",
                "url": "https://pje.trt3.jus.br",
                "description": "PJe — Tribunal Regional do Trabalho 3ª Região",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PROJUDI — TJMG",
                "url": "https://projudi.tjmg.jus.br",
                "description": "Processo Judicial Digital — TJMG (Juizados Especiais)",
                "icon": "document-properties-symbolic",
            },
            {
                "name": "Consulta Processual — TJMG",
                "url": "https://www4.tjmg.jus.br/juridico/sf/proc_movimentacoes.jsp",
                "description": "Consulta de processos — TJMG",
                "icon": "system-search-symbolic",
            },
        ],
    },
    {
        "name": "Rio Grande do Sul",
        "subtitle": "TJRS · TRF4 · TRT4",
        "icon": "mark-location-symbolic",
        "systems": [
            {
                "name": "eProc — TJRS 1ª Instância",
                "url": "https://eproc1g.tjrs.jus.br",
                "description": "eProc 1º Grau — TJRS",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "eProc — TJRS 2ª Instância",
                "url": "https://eproc2g.tjrs.jus.br",
                "description": "eProc 2º Grau — TJRS",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "eProc — TRF4",
                "url": "https://eproc.trf4.jus.br",
                "description": "eProc — Tribunal Regional Federal da 4ª Região",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TRT4 (Rio Grande do Sul)",
                "url": "https://pje.trt4.jus.br",
                "description": "PJe — Tribunal Regional do Trabalho 4ª Região",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "Consulta Processual — TJRS",
                "url": "https://www.tjrs.jus.br/novo/busca/?tb=proc",
                "description": "Consulta de processos — TJRS",
                "icon": "system-search-symbolic",
            },
        ],
    },
    {
        "name": "Paraná",
        "subtitle": "TJPR · TRF4 · TRT9",
        "icon": "mark-location-symbolic",
        "systems": [
            {
                "name": "PROJUDI — TJPR",
                "url": "https://projudi.tjpr.jus.br",
                "description": "Processo Judicial Digital — TJPR",
                "icon": "document-properties-symbolic",
            },
            {
                "name": "PJe — TJPR",
                "url": "https://pje.tjpr.jus.br",
                "description": "PJe — Tribunal de Justiça do Paraná",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TRT9 (Paraná)",
                "url": "https://pje.trt9.jus.br",
                "description": "PJe — Tribunal Regional do Trabalho 9ª Região",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "Consulta Processual — TJPR",
                "url": "https://portal.tjpr.jus.br/jurisprudencia/",
                "description": "Consulta de processos e jurisprudência — TJPR",
                "icon": "system-search-symbolic",
            },
        ],
    },
]

# Flat list of all judicial systems for use by other modules (e.g. Brave config)
JUDICIAL_SYSTEMS: list[dict[str, str]] = [
    system
    for state in JUDICIAL_STATES
    for system in state["systems"]
]
