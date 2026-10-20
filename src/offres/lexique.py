"""Lexique des outils et technologies, avec leurs variantes d'écriture, et extraction par expressions régulières.

C'est la méthode « dictionnaire » de l'étape 4 : simple, explicable, rapide, mais aveugle à tout ce qui n'est pas
dans la liste. Le référentiel ROME couvre les savoir-faire génériques ; ce lexique couvre les outils, que le ROME
nomme rarement.
"""

from __future__ import annotations

import re
import unicodedata

# compétence canonique -> (catégorie, motifs regex appliqués au texte en minuscules sans accents)
LEXIQUE: dict[str, tuple[str, list[str]]] = {
    # Langages
    "Python": ("Langage", [r"\bpython\b"]),
    "SQL": ("Langage", [r"\bsql\b", r"\bt-sql\b", r"\bpl/?sql\b"]),
    "R": ("Langage", [r"\blangage r\b", r"\br ?studio\b", r"\br shiny\b", r"\b(?:python|sql|sas|stata)\s*(?:,|/|et|ou)\s*r\b",
                      r"\br\s*(?:,|/|et|ou)\s*(?:python|sql|sas|stata)\b"]),
    "SAS": ("Langage", [r"\blogiciel sas\b", r"\bsas (?:base|enterprise|guide|viya)\b",
                         r"\b(?:python|sql|r|stata|spss)\s*(?:,|/|et|ou)\s*sas\b", r"\bsas\s*(?:,|/|et|ou)\s*(?:python|sql|r|stata|spss)\b"]),
    "Java": ("Langage", [r"\bjava\b(?!\s*script)"]),
    "JavaScript": ("Langage", [r"\bjavascript\b", r"\bjs\b"]),
    "TypeScript": ("Langage", [r"\btypescript\b"]),
    "PHP": ("Langage", [r"\bphp\b"]),
    "C#": ("Langage", [r"\bc#", r"\bc sharp\b"]),
    "C++": ("Langage", [r"\bc\+\+"]),
    "C": ("Langage", [r"\blangage c\b", r"\bc\s*/\s*c\+\+", r"\b(?:python|java|perl|fortran|rust)\s*(?:,|/|ou|et)\s*c\b(?![+#])"]),
    "Perl": ("Langage", [r"\bperl\b"]),
    "Go": ("Langage", [r"\bgolang\b", r"\blangage go\b"]),
    "Rust": ("Langage", [r"\brust\b"]),
    "Scala": ("Langage", [r"\bscala\b"]),
    "Kotlin": ("Langage", [r"\bkotlin\b"]),
    "Swift": ("Langage", [r"\bswift ?ui\b", r"\blangage swift\b", r"\bswift\s*(?:,|/|ou|et)\s*(?:kotlin|objective-c)\b",
                          r"\b(?:kotlin|objective-c)\s*(?:,|/|ou|et)\s*swift\b"]),
    "Ruby": ("Langage", [r"\bruby\b", r"\bruby on rails\b"]),
    "VBA": ("Langage", [r"\bvba\b", r"\bmacros? excel\b"]),
    "Bash / Shell": ("Langage", [r"\bbash\b", r"\bshell (?:script|unix|linux)", r"\bscripts? shell\b"]),
    "PowerShell": ("Langage", [r"\bpowershell\b"]),
    "COBOL": ("Langage", [r"\bcobol\b"]),
    "ABAP": ("Langage", [r"\babap\b"]),
    "HTML / CSS": ("Langage", [r"\bhtml5?\b", r"\bcss3?\b"]),
    "MATLAB": ("Langage", [r"\bmatlab\b"]),
    # Data et IA
    "pandas": ("Data", [r"\bpandas\b"]),
    "NumPy": ("Data", [r"\bnumpy\b"]),
    "scikit-learn": ("Data", [r"\bscikit[- ]?learn\b", r"\bsklearn\b"]),
    "TensorFlow": ("IA", [r"\btensorflow\b", r"\bkeras\b"]),
    "PyTorch": ("IA", [r"\bpytorch\b"]),
    "Machine learning": ("IA", [r"\bmachine learning\b", r"\bapprentissage automatique\b"]),
    "Deep learning": ("IA", [r"\bdeep learning\b", r"\bapprentissage profond\b", r"\breseaux de neurones\b"]),
    "IA générative / LLM": ("IA", [r"\bllms?\b", r"\bia generative\b", r"\bgenai\b", r"\bgen ai\b", r"\bchatgpt\b",
                                    r"\bgpt-?\d?\b", r"\brag\b", r"\blangchain\b", r"\bprompt(?:ing| engineering)?\b",
                                    r"\bgrands? modeles? de langage\b"]),
    # « IA » seul est trop ambigu (SSIAP, IA-IPR...) : on ne garde que les formes explicites
    "Intelligence artificielle": ("IA", [r"\bintelligence artificielle\b", r"\b(?:outils|solutions|projets|modeles|usages?) d'ia\b",
                                         r"\bl'ia\b(?![- ]ipr)"]),
    "NLP": ("IA", [r"\bnlp\b", r"\btraitement (?:automatique )?du langage\b"]),
    "Computer vision": ("IA", [r"\bcomputer vision\b", r"\bvision par ordinateur\b"]),
    "MLOps": ("IA", [r"\bmlops\b", r"\bmlflow\b", r"\bkubeflow\b"]),
    # « tableaux de bord et statistiques » (suivi d'activité) n'est pas une compétence de statisticien
    "Statistiques": ("Data", [
        r"\b(?:analyses?|methodes?|methodologie|traitements?|modelisation|techniques?|outils|logiciels?|enquetes?) statisti",
        r"\bstatistiques? (?:descriptives?|inferentielles?|bayesiennes?|appliquees?|publiques?|mathematiques?)",
        r"\bstatisticien", r"\beconometri", r"\bdata ?science\b", r"\bsciences? des donnees\b",
    ]),
    "SPSS / Stata": ("Data", [r"\bspss\b", r"\bstata\b"]),
    "SIG (QGIS, ArcGIS)": ("Data", [r"\bqgis\b", r"\barcgis\b", r"\bsig\b", r"\bsystemes? d'information geographique"]),
    "Data visualisation": ("Data", [r"\bdata ?visuali[sz]ation\b", r"\bdataviz\b", r"\bvisualisation de donnees\b"]),
    "Spark": ("Data", [r"\bspark\b", r"\bpyspark\b"]),
    "Hadoop": ("Data", [r"\bhadoop\b", r"\bhive\b", r"\bhdfs\b"]),
    "Kafka": ("Data", [r"\bkafka\b"]),
    "Airflow": ("Data", [r"\bairflow\b"]),
    "dbt": ("Data", [r"\bdbt\b"]),
    "Databricks": ("Data", [r"\bdatabricks\b"]),
    "Snowflake": ("Data", [r"\bsnowflake\b"]),
    "BigQuery": ("Data", [r"\bbigquery\b", r"\bbig query\b"]),
    "ETL / ELT": ("Data", [r"\betl\b", r"\belt\b", r"\btalend\b", r"\binformatica\b", r"\bssis\b"]),
    "Data warehouse": ("Data", [r"\bdata ?warehouse\b", r"\bentrepot de donnees\b", r"\bdatalake\b", r"\bdata lake\b"]),
    "Big data": ("Data", [r"\bbig data\b"]),
    # BI
    "Power BI": ("BI", [r"\bpower ?bi\b"]),
    "Tableau": ("BI", [r"\btableau software\b", r"\btableau desktop\b", r"\b(?:power ?bi|qlik|looker)\s*(?:,|/|ou|et)\s*tableau\b",
                       r"\btableau\s*(?:,|/|ou|et)\s*(?:power ?bi|qlik|looker)\b"]),
    "Qlik": ("BI", [r"\bqlik ?(?:view|sense)?\b"]),
    "Looker": ("BI", [r"\blooker\b"]),
    "Business Objects": ("BI", [r"\bbusiness objects\b", r"\bsap bo\b"]),
    # Bases de données
    "PostgreSQL": ("Base de données", [r"\bpostgre(?:s|sql)\b"]),
    "MySQL": ("Base de données", [r"\bmysql\b", r"\bmariadb\b"]),
    "Oracle": ("Base de données", [r"\boracle\b(?! linux)"]),
    "Access": ("Base de données", [r"\bms access\b", r"\bmicrosoft access\b", r"\b(?:excel|word)\s*(?:,|/|et|ou)\s*access\b",
                                    r"\baccess\s*(?:,|/|et|ou)\s*(?:excel|word)\b", r"\blogiciel access\b"]),
    "SQL Server": ("Base de données", [r"\bsql server\b", r"\bmssql\b"]),
    "MongoDB": ("Base de données", [r"\bmongo ?db\b"]),
    "Elasticsearch": ("Base de données", [r"\belastic ?search\b", r"\bkibana\b"]),
    "Redis": ("Base de données", [r"\bredis\b"]),
    "NoSQL": ("Base de données", [r"\bnosql\b"]),
    # Cloud et DevOps
    "AWS": ("Cloud", [r"\baws\b", r"\bamazon web services\b"]),
    "Azure": ("Cloud", [r"\bazure\b"]),
    "Google Cloud": ("Cloud", [r"\bgcp\b", r"\bgoogle cloud\b"]),
    "Docker": ("DevOps", [r"\bdocker\b", r"\bconteneuris"]),
    "Kubernetes": ("DevOps", [r"\bkubernetes\b", r"\bk8s\b", r"\bopenshift\b"]),
    "Terraform": ("DevOps", [r"\bterraform\b"]),
    "Ansible": ("DevOps", [r"\bansible\b"]),
    "CI/CD": ("DevOps", [r"\bci ?/ ?cd\b", r"\bjenkins\b", r"\bgitlab[- ]ci\b", r"\bgithub actions\b", r"\bintegration continue\b"]),
    "Git": ("DevOps", [r"\bgit\b", r"\bgitlab\b", r"\bgithub\b"]),
    "Linux": ("Système", [r"\blinux\b", r"\bunix\b", r"\bdebian\b", r"\bubuntu\b", r"\bred ?hat\b"]),
    "Windows Server": ("Système", [r"\bwindows server\b", r"\bactive directory\b"]),
    "VMware": ("Système", [r"\bvmware\b", r"\bvirtualisation\b"]),
    "Réseaux": ("Système", [r"\btcp/?ip\b", r"\bcisco\b", r"\breseaux? informatiques?\b", r"\bfirewall\b", r"\bpare-feu\b"]),
    "Cybersécurité": ("Système", [r"\bcybersecurite\b", r"\bsecurite (?:informatique|des systemes d'information)\b",
                                    r"\bsoc\b(?! (?:arm|fpga))", r"\bssi\b",
                                    r"\bpentest\b", r"\biso ?27001\b"]),
    # Web et logiciel
    "React": ("Web", [r"\breact(?:\.?js)?\b"]),
    "Angular": ("Web", [r"\bangular(?:js)?\b"]),
    "Vue.js": ("Web", [r"\bvue\.?js\b"]),
    "Node.js": ("Web", [r"\bnode\.?js\b"]),
    "Django": ("Web", [r"\bdjango\b"]),
    "Flask / FastAPI": ("Web", [r"\bflask\b", r"\bfastapi\b"]),
    "Spring": ("Web", [r"\bspring(?: boot)?\b"]),
    ".NET": ("Web", [r"\.net\b", r"\bdotnet\b", r"\basp\.net\b"]),
    "Symfony": ("Web", [r"\bsymfony\b"]),
    "Laravel": ("Web", [r"\blaravel\b"]),
    "WordPress": ("Web", [r"\bwordpress\b"]),
    "API REST": ("Web", [r"\bapi ?rest\b", r"\brestful\b", r"\bapis?\b"]),
    # « agile » seul est souvent un adjectif (« esprit agile ») : on exige le contexte méthode
    "Agile / Scrum": ("Méthode", [r"\bmethodes? agiles?\b", r"\bmethodologies? agiles?\b", r"\ben mode agile\b",
                                   r"\bscrum\b", r"\bkanban\b", r"\bsafe\b(?= ?(?:framework|agile))"]),
    "Jira": ("Méthode", [r"\bjira\b", r"\bconfluence\b"]),
    # Progiciels et bureautique
    "SAP": ("Progiciel", [r"\bsap\b"]),
    "Salesforce": ("Progiciel", [r"\bsalesforce\b"]),
    "Excel": ("Bureautique", [r"\bexcel\b"]),
    "Pack Office": ("Bureautique", [r"\bpack office\b", r"\bsuite office\b", r"\bmicrosoft office\b", r"\bword\b", r"\bpowerpoint\b",
                                     r"\boutlook\b", r"\bms office\b", r"\boffice 365\b", r"\bmicrosoft 365\b"]),
    "Bureautique (générique)": ("Bureautique", [r"\boutils? bureautiques?\b", r"\blogiciels? bureautiques?\b", r"\bbureautique\b"]),
    "LibreOffice": ("Bureautique", [r"\blibre ?office\b", r"\bopen ?office\b"]),
    "Google Workspace": ("Bureautique", [r"\bgoogle workspace\b", r"\bgoogle sheets?\b"]),
    "AutoCAD": ("CAO", [r"\bautocad\b"]),
    "SolidWorks": ("CAO", [r"\bsolidworks\b"]),
    "CATIA": ("CAO", [r"\bcatia\b"]),
    "Revit / BIM": ("CAO", [r"\brevit\b", r"\bbim\b"]),
    "Adobe (Photoshop, Illustrator...)": ("Création", [r"\bphotoshop\b", r"\billustrator\b", r"\bindesign\b", r"\bsuite adobe\b"]),
    "Figma": ("Création", [r"\bfigma\b"]),
    # « ERP » désigne aussi les établissements recevant du public (sécurité incendie, accessibilité)
    "ERP": ("Progiciel", [r"\b(?:progiciel|logiciel|outil|systeme|solution)s? (?:de gestion integre|erp)\b", r"\berp (?:sap|oracle|odoo)\b",
                          r"\b(?:sap|oracle|odoo|sage|cegid) ?/ ?erp\b", r"\berp\b(?=.{0,40}\b(?:progiciel|sap|logiciel|odoo)\b)"]),
    "CRM": ("Progiciel", [r"\bcrm\b"]),
    "Sage": ("Progiciel", [r"\bsage (?:100|1000|x3|compta\w*|paie|ligne 100)\b", r"\blogiciels? sage\b"]),
    "Cegid": ("Progiciel", [r"\bcegid\b"]),
    # Langues étrangères
    "Anglais": ("Langue", [r"\banglais\b", r"\benglish\b"]),
    "Allemand": ("Langue", [r"\ballemand\b"]),
    "Espagnol": ("Langue", [r"\bespagnol\b"]),
    "Italien": ("Langue", [r"\bitalien\b"]),
}

_COMPILE = {nom: (cat, re.compile("|".join(motifs))) for nom, (cat, motifs) in LEXIQUE.items()}


def normaliser(texte: str) -> str:
    texte = unicodedata.normalize("NFKD", texte.lower())
    return "".join(c for c in texte if not unicodedata.combining(c))


def extraire(texte: str | None) -> list[str]:
    """Compétences du lexique présentes dans le texte, dans l'ordre du lexique."""
    if not texte:
        return []
    t = normaliser(texte)
    return [nom for nom, (_, motif) in _COMPILE.items() if motif.search(t)]


def categorie(nom: str) -> str:
    return LEXIQUE[nom][0]
