"""Utility functions"""

from uuid import UUID
from os import environ
import re
from typing import Optional, Union
from babel.dates import format_date
import iso8601
import json as JSON
import html
from lxml import etree
import pydash as py_
from dateutil import parser, relativedelta
from datetime import datetime, timezone
from furl import furl
from langdetect import detect
from bs4 import BeautifulSoup
import nh3
from commonmeta import (
    Metadata,
    get_one_author,
    validate_url,
    validate_orcid,
    normalize_orcid,
    normalize_id,
    doi_from_url,
)
from commonmeta.constants import Commonmeta
from commonmeta.date_utils import get_date_from_unix_timestamp
from commonmeta.doi_utils import validate_prefix, get_doi_ra
import frontmatter
import pandoc

# from pandoc.types import Str
from sentry_sdk import capture_message


AUTHOR_IDS = {
    "Kristian Garza": "https://orcid.org/0000-0003-3484-6875",
    "Roderic Page": "https://orcid.org/0000-0002-7101-9767",
    "Tejas S. Sathe": "https://orcid.org/0000-0003-0449-4469",
    "Meghal Shah": "https://orcid.org/0000-0002-2085-659X",
    "Liberate Science": "https://ror.org/0342dzm54",
    "Lars Willighagen": "https://orcid.org/0000-0002-4751-4637",
    "Egon Willighagen": "https://orcid.org/0000-0001-7542-0286",
    "Marco Tullney": "https://orcid.org/0000-0002-5111-2788",
    "Andrew Heiss": "https://orcid.org/0000-0002-3948-3914",
    "Sebastian Karcher": "https://orcid.org/0000-0001-8249-7388",
    "Colin Elman": "https://orcid.org/0000-0003-1004-4640",
    "Veronica Herrera": "https://orcid.org/0000-0003-4935-1226",
    "Dessislava Kirilova": "https://orcid.org/0000-0002-3824-9982",
    "Corin Wagen": "https://orcid.org/0000-0003-3315-3524",
    "Adèniké Deane-Pratt": "https://orcid.org/0000-0001-9940-9233",
    "Angela Dappert": "https://orcid.org/0000-0003-2614-6676",
    "Laura Rueda": "https://orcid.org/0000-0001-5952-7630",
    "Rachael Kotarski": "https://orcid.org/0000-0001-6843-7960",
    "Florian Graef": "https://orcid.org/0000-0002-0716-5639",
    "Adam Farquhar": "https://orcid.org/0000-0001-5331-6592",
    "Tom Demeranville": "https://orcid.org/0000-0003-0902-4386",
    "Martin Fenner": "https://orcid.org/0000-0003-1419-2405",
    "Sünje Dallmeier-Tiessen": "https://orcid.org/0000-0002-6137-2348",
    "Maaike Duine": "https://orcid.org/0000-0003-3412-7192",
    "Kirstie Hewlett": "https://orcid.org/0000-0001-5853-0432",
    "Amir Aryani": "https://orcid.org/0000-0002-4259-9774",
    "Xiaoli Chen": "https://orcid.org/0000-0003-0207-2705",
    "Patricia Herterich": "https://orcid.org/0000-0002-4542-9906",
    "Josh Brown": "https://orcid.org/0000-0002-8689-4935",
    "Robin Dasler": "https://orcid.org/0000-0002-4695-7874",
    "Markus Stocker": "https://orcid.org/0000-0001-5492-3212",
    "Robert Petryszak": "https://orcid.org/0000-0001-6333-2182",
    "Robert Huber": "https://orcid.org/0000-0003-3000-0020",
    "Sven Lieber": "https://orcid.org/0000-0002-7304-3787",
    "David M. Shotton": "https://orcid.org/0000-0001-5506-523X",
    "Heinz Pampel": "https://orcid.org/0000-0003-3334-2771",
    "Martin Paul Eve": "https://orcid.org/0000-0002-5589-8511",
    "Matías Castillo-Aguilar": "https://orcid.org/0000-0001-7291-247X",
    "Leiden Madtrics": "https://ror.org/027bh9e22",
    "Elephant in the Lab": "https://ror.org/02h1qnm70",
    "Ben Kaden": "https://orcid.org/0000-0002-8021-1785",
    "Maxi Kindling": "https://orcid.org/0000-0002-0167-0466",
    "LIBREAS": "https://ror.org/01hcx6992",
    "Jorge Saturno": "https://orcid.org/0000-0002-3761-3957",
    "Ted Habermann": "https://orcid.org/0000-0003-3585-6733",
    "Erin Robinson": "https://orcid.org/0000-0001-9998-0114",
    "Mike Taylor": "https://orcid.org/0000-0002-1003-5675",
    "Matt Wedel": "https://orcid.org/0000-0001-6082-3103",
    "Henrique Costa": "https://orcid.org/0000-0003-4591-4044",
    "Bastian Greshake Tzovaras": "https://orcid.org/0000-0002-9925-9623",
    "Stacy McGaugh": "https://orcid.org/0000-0002-9762-0980",
    "Dorothea Strecker": "https://orcid.org/0000-0002-9754-3807",
    "Daniel Beucke": "https://orcid.org/0000-0003-4905-1936",
    "Isabella Meinecke": "https://orcid.org/0000-0001-8337-3619",
    "Marcel Wrzesinski": "https://orcid.org/0000-0002-2343-7905",
    "Heidi Seibold": "https://orcid.org/0000-0002-8960-9642",
    "Layla Michán": "https://orcid.org/0000-0002-5798-662X",
    "Wilma van Wezenbeek": "https://orcid.org/0000-0002-9558-3709",
    "Ross Mounce": "https://orcid.org/0000-0002-3520-2046",
    "Abhishek Tiwari": "https://orcid.org/0000-0003-2222-2395",
    "Cameron Neylon": "https://orcid.org/0000-0002-0068-716X",
    "Reda Sadki": "https://orcid.org/0000-0003-4051-0606",
    "Georg Fischer": "https://orcid.org/0000-0001-5620-5759",
    "Nick Juty": "https://orcid.org/0000-0002-2036-8350",
    "Suzanne Vogt": "https://orcid.org/0000-0001-8866-3199",
    "Sara El-Gebali": "https://orcid.org/0000-0003-1378-5495",
    "Kelly Stathis": "https://orcid.org/0000-0001-6133-4045",
    "Cody Ross": "https://orcid.org/0000-0002-4684-9769",
    "Gabriela Mejias": "https://orcid.org/0000-0002-1598-7181",
    "Josiline Chigwada": "https://orcid.org/0000-0003-0964-3582",
    "Bosun Obileye": "https://orcid.org/0000-0002-1200-0994",
    "John Chodacki": "https://orcid.org/0000-0002-7378-2408",
    "Matt Buys": "https://orcid.org/0000-0001-7234-3684",
    "Dawid Potgieter": "https://orcid.org/0000-0001-8312-2449",
    "Anusuriya Devaraju": "https://orcid.org/0000-0003-0870-3192",
    "Ashwini Sukale": "https://orcid.org/0009-0001-2841-4366",
    "Kudakwashe Siziva": "https://orcid.org/0009-0001-9295-2089",
    "Xiaoli Chen": "https://orcid.org/0000-0003-0207-2705",
    "Mike Bennett": "https://orcid.org/0000-0002-4795-7817",
    "Helena Cousijn": "http://orcid.org/0000-0001-6660-6214",
    "Wendel Chinsamy": "https://orcid.org/0009-0008-9102-7984",
    "Britta Dreyer": "http://orcid.org/0000-0002-0687-5460",
    "Sara El-Gebali": "https://orcid.org/0000-0003-1378-5495",
    "Arturo Garduño-Magaña": "https://orcid.org/0000-0003-0305-9086",
    "Maria Gould": "https://orcid.org/0000-0002-2916-3423",
    "Richard Hallett": "https://orcid.org/0000-0002-8599-0773",
    "Mary Hirsch": "https://orcid.org/0000-0002-6628-8225",
    "Gabriela Mejias": "https://orcid.org/0000-0002-1598-7181",
    "Bryceson Laing": "https://orcid.org/0000-0002-8249-1629",
    "Mohamad Mostafa": "https://orcid.org/0000-0003-0768-6642",
    "Iratxe Puebla": "https://orcid.org/0000-0003-1258-0746",
    "Joseph Rhoads": "https://orcid.org/0000-0001-9871-4850",
    "Katharina Sokoll": "https://orcid.org/0009-0007-7600-1981",
    "Paul Vierkant": "https://orcid.org/0000-0003-4448-3844",
    "Sarala Wimalaratne": "https://orcid.org/0000-0002-5355-2576",
    "Liz Krznarich": "https://orcid.org/0000-0001-6622-4910",
    "Robin Dasler": "https://orcid.org/0000-0002-4695-7874",
    "Trisha Cruse": "https://orcid.org/0000-0002-9300-5278",
    "Laura Rueda": "https://orcid.org/0000-0001-5952-7630",
    "Richard L. Apodaca": "https://orcid.org/0000-0003-3855-9427",
    "Daniella Lowenberg": "https://orcid.org/0000-0003-2255-1869",
}

AUTHOR_NAMES = {
    "GPT-4": "Tejas S. Sathe",
    "Morgan & Ethan": "Morgan Ernest",
    "Marco": "Marco Tullney",
    "NFernan": "Norbisley Fernández",
    "skarcher@syr.edu": "Sebastian Karcher",
    "celman@maxwell.syr.edu": "Colin Elman",
    "colinelman@twcny.rr.com": "Colin Elman",
    "veronica.herrera@uconn.edu": "Veronica Herrera",
    "dessi.kirilova@syr.edu": "Dessislava Kirilova",
    "benosteen": "Ben O'Steen",
    "marilena_daquino": "Marilena Daquino",
    "markmacgillivray": "Mark MacGillivray",
    "richarddjones": "Richard Jones",
    "maaikeduine": "Maaike Duine",
    "suenjedt": "Sünje Dallmeier-Tiessen",
    "kirstiehewlett": "Kirstie Hewlett",
    "pherterich": "Patricia Herterich",
    "adeanepratt": "Adèniké Deane-Pratt",
    "angeladappert": "Angela Dappert",
    "RachaelKotarski": "Rachael Kotarski",
    "fgraef": "Florian Graef",
    "adamfarquhar": "Adam Farquhar",
    "tomdemeranville": "Tom Demeranville",
    "mfenner": "Martin Fenner",
    "davidshotton": "David M. Shotton",
    "meineckei": "Isabella Meinecke",
    "schradera": "Antonia Schrader",
    "arningu": "Ursula Arning",
    "rmounce": "Ross Mounce",
    "pedroandretta": "Pedro Andretta",
    "Ben": "Ben Kaden",
    "maxiki": "Maxi Kindling",
    "libreas": "LIBREAS",
    "szepanski": "Christoph Szepanski",
    "Open Access Brandenburg": "Team OA Brandenburg",
    "Europe PMC team": "Europe PMC Team",
    "yn235": "Yvonne Nobis",
    "eotyrannus": "Darren Naish",
    "tritonstation": "Stacy McGaugh",
    "Maitri": "Open.Make Team",
    "Package Build": "Open.Make Team",
    "Open.Make team": "Open.Make Team",
    "Stephen": "Stephen Curry",
    "aninkov": "Anton Ninkov",
}

AUTHOR_AFFILIATIONS = {
    "https://orcid.org/0000-0003-3585-6733": [
        {
            "name": "Metadata Game Changers",
            "id": "https://ror.org/05bp8ka05",
            "start_date": "2018-01-01",
        }
    ],
    "https://orcid.org/0000-0001-9998-0114": [
        {
            "name": "Metadata Game Changers",
            "id": "https://ror.org/05bp8ka05",
            "start_date": "2020-10-01",
        }
    ],
    "https://orcid.org/0000-0003-1419-2405": [
        {
            "name": "Medizinische Hochschule Hannover",
            "id": "https://ror.org/00f2yqf98",
            "start_date": "2005-09-01",
        },
        {
            "name": "Public Library of Science",
            "id": "https://ror.org/008zgvp64",
            "start_date": "2012-05-01",
        },
        {
            "name": "DataCite",
            "id": "https://ror.org/04wxnsj81",
            "start_date": "2015-08-01",
        },
        {
            "name": "Front Matter",
            "start_date": "2021-08-01",
        },
    ],
    "https://orcid.org/0000-0001-5952-7630": [
        {
            "name": "DataCite",
            "id": "https://ror.org/04wxnsj81",
            "start_date": "2015-08-01",
        },
    ],
    "https://orcid.org/0000-0003-3334-2771": [
        {
            "name": "Humboldt-Universität zu Berlin",
            "id": "https://ror.org/01hcx6992",
            "start_date": "2012-12-01",
        }
    ],
    "https://orcid.org/0000-0002-2343-7905": [
        {
            "name": "Humboldt-Universität zu Berlin",
            "id": "https://ror.org/01hcx6992",
            "start_date": "2023-11-01",
        }
    ],
    "https://orcid.org/0000-0002-7265-1692": [],
    "https://orcid.org/0000-0002-4259-9774": [
        {
            "name": "Australian National University",
            "id": "https://ror.org/019wvm592",
            "start_date": "2012-02-12",
        },
        {
            "name": "Swinburne University of Technology",
            "id": "https://ror.org/031rekg67",
            "start_date": "2018-08-10",
        },
    ],
    "https://orcid.org/0000-0002-8635-8390": [
        {
            "name": "Imperial College London",
            "id": "https://ror.org/041kmwe10",
            "start_date": "1977-10-01",
        }
    ],
    "https://orcid.org/0000-0002-7101-9767": [
        {
            "name": "University of Glasgow",
            "id": "https://ror.org/00vtgdb53",
            "start_date": "1995-01-01",
        }
    ],
    "https://orcid.org/0000-0001-6444-1436": [
        {
            "name": "GigaScience Press",
            "id": "https://ror.org/03yty8687",
            "start_date": "2010-10-01",
        }
    ],
    "https://orcid.org/0000-0002-5192-9835": [
        {
            "name": "GigaScience Press",
            "id": "https://ror.org/03yty8687",
            "start_date": "2016-05-01",
        }
    ],
    "https://orcid.org/0000-0002-1335-0881": [
        {
            "name": "GigaScience Press",
            "id": "https://ror.org/03yty8687",
            "start_date": "2013-03-01",
        }
    ],
    "https://orcid.org/0000-0002-9373-4622": [
        {
            "name": "University of Camagüey",
            "id": "https://ror.org/040qyzk67",
            "start_date": "2008-10-01",
        }
    ],
    "https://orcid.org/0000-0001-5506-523X": [
        {
            "name": "University of Oxford",
            "id": "https://ror.org/052gg0110",
            "start_date": "1981-01-01",
        }
    ],
    "https://orcid.org/0000-0002-5427-8951": [
        {
            "name": "rOpenSci",
            "start_date": "2016-09-01",
        },
        {
            "name": "Openscapes",
            "start_date": "2022-04-01",
        },
    ],
    "https://orcid.org/0000-0002-7304-3787": [
        {
            "name": "Royal Library of Belgium",
            "id": "https://ror.org/0105w2p42",
            "start_date": "2021-07-01",
        }
    ],
    "https://orcid.org/0000-0002-3948-3914": [
        {
            "name": "Georgia State University",
            "id": "https://ror.org/03qt6ba18",
            "start_date": "2019-08-01",
        }
    ],
    "https://orcid.org/0000-0002-7378-2408": [
        {
            "name": "University of California Office of the President",
            "id": "https://ror.org/00dmfq477",
            "start_date": "2015-10-01",
        }
    ],
    "https://orcid.org/0000-0003-2255-1869": [
        {
            "name": "University of California Office of the President",
            "id": "https://ror.org/00dmfq477",
            "start_date": "2017-02-03",
        }
    ],
    "https://orcid.org/0000-0001-8249-1752": [
        {
            "name": "Leiden University",
            "id": "https://ror.org/027bh9e22",
            "start_date": "2009-06-01",
        }
    ],
    "https://orcid.org/0000-0002-2947-9444": [
        {
            "name": "Leiden University",
            "id": "https://ror.org/027bh9e22",
            "start_date": "2023-10-01",
        }
    ],
    "https://orcid.org/0000-0002-6527-7778": [
        {
            "name": "Leiden University",
            "id": "https://ror.org/027bh9e22",
            "start_date": "2020-01-01",
        }
    ],
    "https://orcid.org/0000-0002-7465-6462": [
        {
            "name": "Leiden University",
            "id": "https://ror.org/027bh9e22",
            "start_date": "2009-01-01",
        }
    ],
    "https://orcid.org/0000-0001-8448-4521": [
        {
            "name": "Leiden University",
            "id": "https://ror.org/027bh9e22",
            "start_date": "2009-06-01",
        }
    ],
    "https://orcid.org/0000-0003-4853-2463": [
        {
            "name": "Leiden University",
            "id": "https://ror.org/027bh9e22",
            "start_date": "2021-01-05",
        }
    ],
    "https://orcid.org/0000-0002-1598-7181": [
        {
            "name": "DataCite",
            "id": "https://ror.org/04wxnsj81",
            "start_date": "2022-05-11",
        }
    ],
    "https://orcid.org/0000-0003-3484-6875": [
        {
            "name": "DataCite",
            "id": "https://ror.org/04wxnsj81",
            "start_date": "2016-08-01",
        }
    ],
    "https://orcid.org/0000-0002-1003-5675": [
        {
            "name": "University of Portsmouth",
            "id": "https://ror.org/03ykbk197",
            "start_date": "2004-01-01",
        },
        {
            "name": "University College London",
            "id": "https://ror.org/02jx3x895",
            "start_date": "2009-05-16",
        },
        {
            "name": "University of Bristol",
            "id": "https://ror.org/0524sp257",
            "start_date": "2011-06-07",
        },
    ],
    "https://orcid.org/0000-0001-6082-3103": [
        {
            "name": "University of California, Merced",
            "id": "https://ror.org/00d9ah105",
            "start_date": "2007-08-01",
        },
        {
            "name": "Western University of Health Sciences",
            "id": "https://ror.org/05167c961",
            "start_date": "2008-08-01",
        },
    ],
    "https://orcid.org/0000-0001-5934-7525": [
        {
            "name": "University of Illinois Urbana-Champaign",
            "id": "https://ror.org/047426m28",
            "start_date": "2016-03-01",
        }
    ],
    "https://orcid.org/0000-0002-8424-0604": [
        {
            "name": "Polyneme LLC",
            "start_date": "2020-07-01",
        }
    ],
    "https://orcid.org/0000-0002-5589-8511": [
        {
            "name": "Queen Mary University of London",
            "id": "https://ror.org/026zzn846",
            "start_date": "2005-09-01",
        },
        {
            "name": "University of Sussex",
            "id": "https://ror.org/00ayhx656",
            "start_date": "2009-09-01",
        },
        {
            "name": "University of Lincoln",
            "id": "https://ror.org/03yeq9x20",
            "start_date": "2013-01-07",
        },
        {
            "name": "Birkbeck, University of London",
            "id": "https://ror.org/02mb95055",
            "start_date": "2015-05-01",
        },
    ],
    "https://orcid.org/0009-0004-4949-9284": [
        {
            "name": "Australian National University",
            "id": "https://ror.org/019wvm592",
            "start_date": "2022-01-01",
        },
    ],
    "https://orcid.org/0009-0002-2884-2771": [
        {
            "name": "Australian National University",
            "id": "https://ror.org/019wvm592",
            "start_date": "2023-02-01",
        },
    ],
    "https://orcid.org/0009-0003-5348-4264": [
        {
            "name": "Australian National University",
            "id": "https://ror.org/019wvm592",
        },
    ],
    "https://orcid.org/0009-0009-8807-5982": [
        {
            "name": "Australian National University",
            "id": "https://ror.org/019wvm592",
            "start_date": "2023-02-01",
        },
    ],
    "https://orcid.org/0009-0004-7109-5403": [
        {
            "name": "Australian National University",
            "id": "https://ror.org/019wvm592",
        },
    ],
    "https://orcid.org/0009-0003-3823-6609": [
        {
            "name": "Australian National University",
            "id": "https://ror.org/019wvm592",
            "start_date": "2023-07-01",
        },
    ],
    "https://orcid.org/0009-0003-3823-6609": [
        {
            "name": "Australian National University",
            "id": "https://ror.org/019wvm592",
            "start_date": "2023-07-01",
        },
    ],
    "https://orcid.org/0009-0009-9720-9233": [
        {
            "name": "Swinburne University of Technology",
            "id": "https://ror.org/031rekg67",
            "start_date": "2023-06-16",
        },
    ],
    "https://orcid.org/0009-0008-8672-3168": [
        {
            "name": "Swinburne University of Technology",
            "id": "https://ror.org/031rekg67",
            "start_date": "2024-01-01",
        },
    ],
    "https://orcid.org/0000-0001-9940-9233": [
        {
            "name": "ORCID",
            "id": "https://ror.org/04fa4r544",
            "start_date": "2016-12-01",
        }
    ],
    "https://orcid.org/0000-0002-8689-4935": [
        {
            "name": "ORCID",
            "id": "https://ror.org/04fa4r544",
            "start_date": "2014-05-01",
        },
        {
            "name": "Crossref",
            "id": "https://ror.org/02twcfp32",
            "start_date": "2019-05-01",
        },
    ],
    "https://orcid.org/0000-0003-0207-2705": [
        {
            "name": "European Organization for Nuclear Research",
            "id": "https://ror.org/01ggx4157",
            "start_date": "2015-06-01",
        },
        {
            "name": "DataCite",
            "id": "https://ror.org/04wxnsj81",
            "start_date": "2021-10-01",
        },
    ],
    "https://orcid.org/0000-0002-6137-2348": [
        {
            "name": "European Organization for Nuclear Research",
            "id": "https://ror.org/01ggx4157",
            "start_date": "2009-12-01",
        }
    ],
    "https://orcid.org/0000-0002-4542-9906": [
        {
            "name": "European Organization for Nuclear Research",
            "id": "https://ror.org/01ggx4157",
            "start_date": "2012-02-01",
        }
    ],
    "https://orcid.org/0000-0003-3412-7192": [
        {
            "name": "ORCID",
            "id": "https://ror.org/04fa4r544",
            "start_date": "2016-02-01",
        },
        {
            "name": "Freie Universität Berlin",
            "id": "https://ror.org/046ak2485",
            "start_date": "2022-01-07",
        },
    ],
    "https://orcid.org/0000-0003-0902-4386": [
        {
            "name": "ORCID",
            "id": "https://ror.org/04fa4r544",
            "start_date": "2015-06-10",
        }
    ],
    "https://orcid.org/0000-0001-5492-3212": [
        {
            "name": "University of Bremen",
            "id": "https://ror.org/04ers2y35",
            "start_date": "2016-02-01",
        },
        {
            "name": "Technische Informationsbibliothek (TIB)",
            "id": "https://ror.org/04aj4c181",
            "start_date": "2017-12-01",
        },
    ],
    "https://orcid.org/0000-0001-5853-0432": [
        {
            "name": "British Library",
            "id": "https://ror.org/05dhe8b71",
            "start_date": "2016-02-12",
        }
    ],
    "https://orcid.org/0000-0001-5331-6592": [
        {
            "name": "British Library",
            "id": "https://ror.org/05dhe8b71",
            "start_date": "2004-12-01",
        }
    ],
    "https://orcid.org/0000-0001-7542-0286": [
        {
            "name": "Maastricht University",
            "id": "https://ror.org/02jz4aj89",
            "start_date": "2012-01-01",
        }
    ],
    "https://orcid.org/0000-0002-9762-0980": [
        {
            "name": "Case Western Reserve University",
            "id": "https://ror.org/051fd9666",
            "start_date": "2012-08-25",
        }
    ],
    "https://orcid.org/0000-0001-8337-3619": [
        {
            "name": "Hamburg State and University Library",
            "id": "https://ror.org/00pwcvj19",
            "start_date": "2006-07-01",
        }
    ],
    "https://orcid.org/0000-0003-4905-1936": [
        {
            "name": "Göttingen State and University Library",
            "id": "https://ror.org/05745n787",
            "start_date": "2007-07-01",
        }
    ],
    "https://orcid.org/0000-0003-0330-9428": [
        {
            "name": "Centre de Biophysique Moléculaire",
            "id": "https://ror.org/02dpqcy73",
            "start_date": "1998-04-01",
        }
    ],
    "https://orcid.org/0000-0002-5798-662X": [
        {
            "name": "Universidad Nacional Autónoma de México",
            "id": "https://ror.org/01tmp8f25",
            "start_date": "2003-01-01",
        }
    ],
    "https://orcid.org/0000-0002-9558-3709": [
        {
            "name": "Delft University of Technology",
            "id": "https://ror.org/02e2c7k09",
            "start_date": "2006-08-01",
        },
        {
            "name": "Vrije Universiteit Amsterdam",
            "id": "https://ror.org/008xxew50",
            "start_date": "2020-09-01",
        },
        {
            "name": "SURF",
            "id": "https://ror.org/009vhk114",
            "start_date": "2023-07-01",
        },
        {
            "name": "National Library of the Netherlands",
            "id": "https://ror.org/02w4jbg70",
            "start_date": "2024-09-01",
        },
    ],
    "https://orcid.org/0000-0002-3761-3957": [
        {
            "name": "Physikalisch-Technische Bundesanstalt",
            "id": "https://ror.org/05r3f7h03",
            "start_date": "2018-01-01",
        }
    ],
    "https://orcid.org/0000-0002-0068-716X": [
        {
            "name": "Science and Technology Facilities Council",
            "id": "https://ror.org/057g20z61",
            "start_date": "2005-09-01",
        },
        {
            "name": "Public Library of Science",
            "id": "https://ror.org/008zgvp64",
            "start_date": "2012-07-12",
        },
        {
            "name": "Curtin University",
            "id": "https://ror.org/02n415q13",
            "start_date": "2015-07-21",
        },
    ],
    "https://orcid.org/0000-0003-4051-0606": [
        {
            "name": "The Geneva Learning Foundation",
            "id": "https://ror.org/04h13ss13",
            "start_date": "2016-03-01",
        }
    ],
    "https://orcid.org/0000-0003-1378-5495": [
        {
            "name": "DataCite",
            "id": "https://ror.org/04wxnsj81",
            "start_date": "2023-11-01",
        }
    ],
    "https://orcid.org/0000-0001-6133-4045": [
        {
            "name": "DataCite",
            "id": "https://ror.org/04wxnsj81",
            "start_date": "2022-04-01",
        }
    ],
    "https://orcid.org/0000-0001-7234-3684": [
        {
            "name": "DataCite",
            "id": "https://ror.org/04wxnsj81",
            "start_date": "2019-10-15",
        }
    ],
    "https://orcid.org/0000-0001-7824-7650": [
        {
            "name": "University of Regensburg",
            "id": "https://ror.org/01eezs655",
            "start_date": "2012-10-01",
        }
    ],
    "https://orcid.org/0000-0002-2405-7816": [
        {
            "name": "Scholarly Publishing and Academic Resources Coalition",
            "id": "https://ror.org/01dktcn28",
            "start_date": "2022-02-07",
        }
    ],
    "https://orcid.org/0000-0001-9039-9219": [
        {
            "name": "ASAPbio",
            "id": "https://ror.org/05k4vg494",
            "start_date": "2023-07-13",
        }
    ],
    "https://orcid.org/0000-0003-2797-1686": [
        {
            "name": "Ottawa Heart Institute",
            "id": "https://ror.org/00h533452",
            "start_date": "2021-11-08",
        }
    ],
    "https://orcid.org/0000-0002-7971-1678": [
        {
            "name": "ASAPbio",
            "id": "https://ror.org/05k4vg494",
            "start_date": "2024-05-01",
        }
    ],
    "https://orcid.org/0000-0002-5965-6560": [
        {
            "name": "Sesame Open Science",
            "start_date": "2022-07-01",
        }
    ],
    "https://orcid.org/0000-0003-4817-8206": [
        {
            "name": "F1000",
            "id": "https://ror.org/019tc7185",
            "start_date": "2015-11-01",
        }
    ],
    "https://orcid.org/0000-0003-1649-0879": [
        {
            "name": "Federation of Finnish Learned Societies",
            "id": "https://ror.org/02cdzet69",
            "start_date": "2018-01-01",
        }
    ],
    "https://orcid.org/0000-0002-4900-936X": [
        {
            "name": "Howard Hughes Medical Institute",
            "id": "https://ror.org/006w34k90",
            "start_date": "2016-09-01",
        }
    ],
    "https://orcid.org/0000-0002-5337-4722": [
        {
            "name": "Universidad Carlos III de Madrid",
            "id": "https://ror.org/03ths8210",
            "start_date": "2008-05-08",
        }
    ],
}


EXCLUDED_TAGS = ["Uncategorized", "Uncategorised", "Blog", "doi", "justdoi"]

FOS_MAPPINGS = {
    "naturalSciences": "Natural sciences",
    "mathematics": "Mathematics",
    "computerAndInformationSciences": "Computer and information sciences",
    "physicalSciences": "Physical sciences",
    "chemicalSciences": "Chemical sciences",
    "earthAndRelatedEnvironmentalSciences": "Earth and related environmental sciences",
    "biologicalSciences": "Biological sciences",
    "otherNaturalSciences": "Other natural sciences",
    "engineeringAndTechnology": "Engineering and technology",
    "civilEngineering": "Civil engineering",
    "electricalEngineering": "Electrical engineering, electronic engineering, information engineering",
    "mechanicalEngineering": "Mechanical engineering",
    "chemicalEngineering": "Chemical engineering",
    "materialsEngineering": "Materials engineering",
    "medicalEngineering": "Medical engineering",
    "environmentalEngineering": "Environmental engineering",
    "environmentalBiotechnology": "Environmental biotechnology",
    "industrialBiotechnology": "Industrial biotechnology",
    "nanoTechnology": "Nano technology",
    "otherEngineeringAndTechnologies": "Other engineering and technologies",
    "medicalAndHealthSciences": "Medical and health sciences",
    "basicMedicine": "Basic medicine",
    "clinicalMedicine": "Clinical medicine",
    "healthSciences": "Health sciences",
    "healthBiotechnology": "Health biotechnology",
    "otherMedicalSciences": "Other medical sciences",
    "agriculturalSciences": "Agricultural sciences",
    "agricultureForestryAndFisheries": "Agriculture, forestry, and fisheries",
    "animalAndDairyScience": "Animal and dairy science",
    "veterinaryScience": "Veterinary science",
    "agriculturalBiotechnology": "Agricultural biotechnology",
    "otherAgriculturalSciences": "Other agricultural sciences",
    "socialScience": "Social science",
    "socialSciences": "Social science",
    "psychology": "Psychology",
    "economicsAndBusiness": "Economics and business",
    "educationalSciences": "Educational sciences",
    "sociology": "Sociology",
    "law": "Law",
    "politicalScience": "Political science",
    "socialAndEconomicGeography": "Social and economic geography",
    "mediaAndCommunications": "Media and communications",
    "otherSocialSciences": "Other social sciences",
    "humanities": "Humanities",
    "historyAndArchaeology": "History and archaeology",
    "languagesAndLiterature": "Languages and literature",
    "philosophyEthicsAndReligion": "Philosophy, ethics and religion",
    "artsArtsHistoryOfArtsPerformingArtsMusic": "Arts (arts, history of arts, performing arts, music)",
    "otherHumanities": "Other humanities",
}


def wrap(item) -> list:
    """Turn None, dict, or list into list"""
    if item is None:
        return []
    if isinstance(item, list):
        return item
    return [item]


def compact(dict_or_list: Union[dict, list]) -> Optional[Union[dict, list]]:
    """Remove None from dict or list"""
    if isinstance(dict_or_list, dict):
        return {k: v for k, v in dict_or_list.items() if v is not None}
    if isinstance(dict_or_list, list):
        lst = [compact(i) for i in dict_or_list]
        return lst if len(lst) > 0 else None

    return None


def normalize_author(
    name: str, published_at: int = 0, url: Optional[str] = None
) -> dict:
    """Normalize author name and url. Strip text after comma
    if suffix is an academic title. Lookup affiliation based on name and publication date."""
    if isinstance(name, dict):
        url = name.get("url", None)
        name = name.get("name", None)

    if isinstance(name, str) and name.split(", ", maxsplit=1)[-1] in ["MD", "PhD"]:
        name = name.split(", ", maxsplit=1)[0]

    _name = AUTHOR_NAMES.get(name, None) or name
    _url = url if url and validate_orcid(url) else AUTHOR_IDS.get(_name, None)
    affiliation = AUTHOR_AFFILIATIONS.get(_url, None)
    if affiliation is not None and len(affiliation) > 0 and published_at > 0:
        affiliation = [
            i
            for i in affiliation
            if unix_timestamp(i.get("start_date", 0)) < published_at
        ]
        affiliation = (
            [py_.pick(affiliation[-1], ["id", "name"])] if affiliation else None
        )
    return compact({"name": _name, "url": _url, "affiliation": affiliation})


def get_date(date: str):
    """Get iso8601 date from string."""
    if not date:
        return None
    try:
        return parser.parse(date).isoformat("T", "seconds")
    except Exception as e:
        print(e)
        return None


def unix_timestamp(date_str: Optional[str]) -> int:
    """convert iso8601 date to unix timestamp"""
    if date_str is None:
        return 0
    try:
        dt = iso8601.parse_date(date_str)
        return int(dt.timestamp())
    except ValueError as e:
        print(e)
        return 0


def format_datetime(date_str: str, lc: str = "en") -> str:
    """convert iso8601 date to formatted date"""
    try:
        dt = iso8601.parse_date(date_str)
        return format_date(dt, format="long", locale=lc)
    except ValueError as e:
        print(e)
        return "January 1, 1970"


def end_of_date(date_str: str) -> str:
    """convert iso8601 date to end of day/month/year"""
    try:
        date = date_str.split("-")
        dt = iso8601.parse_date(date_str)
        month, day, hour, minute, second = (
            dt.month,
            dt.day,
            dt.hour,
            dt.minute,
            dt.second,
        )
        month = 12 if len(date) < 2 else month
        day = 31 if len(date) < 3 else day
        hour = 23 if hour == 0 else hour
        minute = 59 if minute == 0 else minute
        second = 59 if second == 0 else second
        dt = dt + relativedelta.relativedelta(
            month=month, day=day, hour=hour, minute=minute, second=second
        )
        return dt.isoformat("T", "seconds")
    except ValueError as e:
        print(e)
        return "1970-01-01T00:00:00"


def format_authors(authors):
    """Extract author names"""

    def format_author(author):
        return author.get("name", None)

    return [format_author(x) for x in authors]


def format_authors_full(authors):
    """Parse author names into given and family names"""

    def format_author(author):
        meta = get_one_author(author)
        given_names = meta.get("givenName", None)
        surname = meta.get("familyName", None)
        name = meta.get("name", None)
        orcid = validate_orcid(author.get("url", None))
        return compact(
            {
                "orcid": orcid,
                "given-names": given_names,
                "surname": surname,
                "name": name,
            }
        )

    return [format_author(x) for x in authors]


def format_authors_commonmeta(authors):
    """Extract author names"""

    def format_author(author):
        return get_one_author(author)

    return [format_author(x) for x in authors]


def format_license(authors, date, rights):
    """Generate license string"""
    if rights == "https://creativecommons.org/publicdomain/zero/1.0/legalcode":
        return """This is an open access article, free of all copyright, 
    and may be freely reproduced, distributed, transmitted, modified, 
    built upon, or otherwise used by anyone for any lawful purpose."""

    auth = format_authors(authors)
    length = len(auth)
    year = date[:4]
    if length == 0:
        auth = ""
    if length > 0:
        auth = auth[0]
    if length > 1:
        auth = auth + " et al."
    return f'Copyright <span class="copyright">©</span> {auth} {year}.'


def format_relationships(relationships):
    "Format relationships metadata"

    def format_relationship(relationship):
        if relationship.get("type", None) == "IsIdenticalTo":
            return {"identical": relationship.get("url", None)}
        elif relationship.get("type", None) == "IsPreprintOf":
            return {"preprint": relationship.get("url", None)}
        elif relationship.get("type", None) == "HasAward":
            return {"funding": relationship.get("url", None)}

    return [format_relationship(x) for x in relationships]


def extract_atom_authors(author_dict):
    """Extract multiple authors from atom feed dict"""

    name = author_dict.get("name", None)
    uri = author_dict.get("uri", None)
    if isinstance(name, str):
        names = re.split(" and |, ", name)
        if len(names) > 1:
            return [{"name": x} for x in names]
        return [{"name": name, "uri": uri}]
    return []


def format_authors_with_orcid(authors):
    """Parse author names into names and orcid"""

    def format_author(author):
        name = author.get("name", None)
        orcid = normalize_orcid(author.get("url", None))
        return compact(
            {
                "orcid": orcid,
                "name": name,
            }
        )

    return [format_author(x) for x in authors]


def validate_uuid(slug: str) -> bool:
    """validate uuid"""
    try:
        UUID(slug, version=4)
        return True
    except ValueError:
        return False


def start_case(content: str) -> str:
    """Capitalize first letter of each word without lowercasing the rest"""

    def capitalize(word):
        return word[:1].upper() + word[1:]

    words = content.split(" ")
    return " ".join([capitalize(word) for word in words])


def normalize_tag(tag: str) -> str:
    """Normalize tag"""
    fixed_tags = {
        "aPKC": "aPKC",
        "CrossRef": "Crossref",
        "DataCite": "DataCite",
        "EU": "EU",
        "USA": "USA",
        "OSTP": "OSTP",
        "ElasticSearch": "ElasticSearch",
        "FoxP": "FoxP",
        "GigaByte": "GigaByte",
        "GigaDB": "GigaDB",
        "GraphQL": "GraphQL",
        "JATS": "JATS",
        "JISC": "JISC",
        "JSON-LD": "JSON-LD",
        "microCT": "MicroCT",
        "MTE14": "MTE14",
        "Pre-Print": "Preprint",
        "Q&A": "Q&A",
        "ResearchGate": "ResearchGate",
        "RStats": "RStats",
        "ScienceEurope": "Science Europe",
        "TreeBASE": "TreeBASE",
        "Web 2.0": "Web 2.0",
        "WikiCite": "WikiCite",
        "WikiData": "WikiData",
    }

    tag = html.unescape(tag)
    tag = tag.replace("#", "")
    return fixed_tags.get(tag, start_case(tag))


def convert_to_commonmeta(meta: dict) -> Commonmeta:
    """Convert post metadata to commonmeta format"""

    doi = doi_from_url(meta.get("doi"))
    published = get_date_from_unix_timestamp(meta.get("published_at", 0))
    updated = get_date_from_unix_timestamp(meta.get("updated_at", None))
    container_title = py_.get(meta, "blog.title")
    identifier = py_.get(meta, "blog.issn")
    identifier_type = "ISSN" if identifier else None
    subjects = py_.human_case(py_.get(meta, "blog.category"))
    publisher = py_.get(meta, "blog.title")
    provider = get_known_doi_ra(doi) or get_doi_ra(doi)
    alternate_identifiers = [
        {"alternateIdentifier": meta.get("id"), "alternateIdentifierType": "UUID"}
    ]
    return {
        "id": meta.get("doi", None) or meta.get("id", None),
        "url": meta.get("url", None),
        "type": "Article",
        "contributors": format_authors_commonmeta(meta.get("authors", None)),
        "titles": [{"title": meta.get("title", None)}],
        "descriptions": [
            {"description": meta.get("summary", None), "descriptionType": "Summary"}
        ],
        "date": {"published": published, "updated": updated},
        "publisher": {
            "name": publisher,
        },
        "container": compact(
            {
                "type": "Periodical",
                "title": container_title,
                "identifier": identifier,
                "identifierType": identifier_type,
            }
        ),
        "subjects": [{"subject": subjects}],
        "language": meta.get("language", None),
        "references": meta.get("reference", None),
        "funding_references": [],
        "license": {
            "id": "CC-BY-4.0"
            if py_.get(meta, "blog.license")
            == "https://creativecommons.org/licenses/by/4.0/legalcode"
            else "CC0-1.0",
            "url": py_.get(meta, "blog.license"),
        },
        "provider": provider,
        "alternateIdentifiers": alternate_identifiers,
        "files": [
            {
                "url": meta.get("url", None),
                "mimeType": "text/html",
            },
            {
                "url": f"https://api.rogue-scholar.org/posts/{doi}.md",
                "mimeType": "text/plain",
            },
            {
                "url": f"https://api.rogue-scholar.org/posts/{doi}.pdf",
                "mimeType": "application/pdf",
            },
            {
                "url": f"https://api.rogue-scholar.org/posts/{doi}.epub",
                "mimeType": "application/epub+zip",
            },
            {
                "url": f"https://api.rogue-scholar.org/posts/{doi}.xml",
                "mimeType": "application/xml",
            },
        ],
        "schema_version": "https://commonmeta.org/commonmeta_v0.12",
    }


def get_formatted_metadata(
    meta: dict = {},
    format_: str = "commonmeta",
    style: str = "apa",
    locale: str = "en-US",
):
    """use commonmeta library to get metadata in various formats.
    format_ can be bibtex, ris, csl, citation, with bibtex as default."""

    content_types = {
        "commonmeta": "application/vnd.commonmeta+json",
        "bibtex": "application/x-bibtex",
        "ris": "application/x-research-info-systems",
        "csl": "application/vnd.citationstyles.csl+json",
        "schema_org": "application/vnd.schemaorg.ld+json",
        "datacite": "application/vnd.datacite.datacite+json",
        "crossref_xml": "application/vnd.crossref.unixref+xml",
        "citation": f"text/x-bibliography; style={style}; locale={locale}",
    }
    content_type = content_types.get(format_)
    subject = Metadata(meta, via="commonmeta")
    doi = doi_from_url(subject.id) if subject.id else None
    basename = doi_from_url(doi).replace("/", "-") if doi else subject.id
    if format_ == "commonmeta":
        ext = "json"
        result = subject.write()
    elif format_ == "csl":
        ext = "json"
        result = subject.write(to="csl")
    elif format_ == "ris":
        ext = "ris"
        result = subject.write(to="ris")
    elif format_ == "bibtex":
        ext = "bib"
        result = subject.write(to="bibtex")
    elif format_ == "schema_org":
        ext = "jsonld"
        result = subject.write(to="schema_org")
    elif format_ == "crossref_xml":
        ext = "xml"
        result = subject.write(to="crossref_xml")
    elif format_ == "datacite":
        ext = "json"
        result = subject.write(to="datacite")
    else:
        ext = "txt"
        # workaround for properly formatting blog posts
        subject.type = "JournalArticle"
        result = subject.write(to="citation", style=style, locale=locale)
    options = {
        "Content-Type": content_type,
        "Content-Disposition": f"attachment; filename={basename}.{ext}",
    }
    return {"doi": doi, "data": result.strip(), "options": options}


def normalize_url(url: Optional[str], secure=False, lower=False) -> Optional[str]:
    """Normalize URL"""
    if url is None or not isinstance(url, str):
        return None
    try:
        # add scheme if missing, workaround for adding scheme via furl
        if not (url.startswith("http") or url.startswith("https")):
            url = "https://" + url
        f = furl(url)
        f.path.normalize()

        # remove index.html
        if f.path.segments and f.path.segments[-1] in ["index.html"]:
            f.path.segments.pop(-1)

        # remove fragments
        f.remove(fragment=True)

        # remove specific query parameters
        f.remove(
            [
                "origin",
                "ref",
                "referrer",
                "source",
                "utm_content",
                "utm_medium",
                "utm_campaign",
                "utm_source",
            ]
        )
        if secure and f.scheme == "http":
            f.set(scheme="https")
        if lower:
            return f.url.lower().strip("/")
        return f.url.strip("/")
    except ValueError:
        capture_message(f"Error normalizing url {url}", "warning")
        return None


def get_src_url(src: str, url: str, home_page_url: str):
    """Get src url"""

    if is_valid_url(src):
        return src

    if src and src.startswith("/"):
        f = furl(home_page_url)
        f.path = ""
        url = f.url
    else:
        url = url + "/"
    return url + src


def is_valid_url(url: str) -> bool:
    """Check if url is valid. Use https as default scheme
    for relative urls starting with //"""
    try:
        f = furl(url)
        if f.scheme is None and f.host is not None:
            return True
        return f.scheme in ["http", "https", "data", "mailto"]
    except Exception:
        return False


def is_local():
    """Rogue Scholar API runs at localhost"""
    return environ["QUART_INVENIORDM_API"] == "https://localhost"


def detect_language(text: str) -> str:
    """Detect language"""

    try:
        return detect(text)
    except Exception as e:
        print(e)
        return "en"


def get_soup(content_html: str) -> Optional[BeautifulSoup]:
    """Get soup from html"""
    try:
        soup = BeautifulSoup(content_html, "html.parser")
        return soup
    except Exception as e:
        print(e)
        return content_html


def fix_xml(x):
    p = etree.fromstring(x, parser=etree.XMLParser(recover=True))
    return etree.tostring(p)


def get_markdown(content_html: str) -> str:
    """Get markdown from html"""
    try:
        doc = pandoc.read(content_html, format="html")
        return pandoc.write(doc, format="commonmark_x")
    except Exception as e:
        print(e)
        return ""


def write_html(markdown: str):
    """Get html from markdown"""
    try:
        doc = pandoc.read(markdown, format="commonmark_x")
        return pandoc.write(doc, format="html")
    except Exception as e:
        print(e)
        return ""


def write_epub(markdown: str):
    """Get epub from markdown"""
    try:
        doc = pandoc.read(markdown, format="commonmark_x")
        return pandoc.write(doc, format="epub")
    except Exception as e:
        print(e)
        return ""


def write_pdf(markdown: str):
    """Get pdf from markdown"""
    try:
        doc = pandoc.read(markdown, format="commonmark_x")
        return pandoc.write(
            doc,
            format="pdf",
            options=[
                "--pdf-engine=weasyprint",
                "--pdf-engine-opt=--pdf-variant=pdf/ua-1",
                f"--data-dir={environ['QUART_PANDOC_DATA_DIR']}",
                "--template=pandoc/default.html5",
                "--css=pandoc/style.css",
            ],
        ), None
    except Exception as e:
        print(e)
        return "", e


def write_jats(markdown: str):
    """Get jats from markdown"""
    try:
        doc = pandoc.read(markdown, format="commonmark_x")
        return pandoc.write(doc, format="jats", options=["--standalone"])
    except Exception as e:
        print(e)
        return ""


def format_markdown(content: str, metadata) -> frontmatter.Post:
    """format markdown"""
    post = frontmatter.Post(content, **metadata)
    post["date"] = datetime.fromtimestamp(
        metadata.get("date", 0), tz=timezone.utc
    ).isoformat("T", "seconds")
    post["date_updated"] = datetime.fromtimestamp(
        metadata.get("date_updated", 0), tz=timezone.utc
    ).isoformat("T", "seconds")
    post["issn"] = py_.get(metadata, "blog.issn")
    post["rights"] = py_.get(metadata, "blog.license")
    post["summary"] = metadata.get("summary", "")
    if post.get("abstract", None) is not None:
        post["abstract"] = metadata.get("abstract")
    return post


def get_known_doi_ra(doi: str) -> Optional[str]:
    """Get DOI registration agency from prefixes used in Rogue Scholar"""
    crossref_prefixes = [
        "10.53731",
        "10.54900",
        "10.59348",
        "10.59349",
        "10.59350",
    ]
    datacite_prefixes = [
        "10.34732",
        "10.57689",
        "10.58079",
    ]
    if doi is None:
        return None
    prefix = validate_prefix(doi)
    if prefix is None:
        return None
    if prefix in crossref_prefixes:
        return "Crossref"
    if prefix in datacite_prefixes:
        return "DataCite"
    return None


def translate_titles(markdown):
    """Translate titles into respective language"""
    lastsep = {"en": "and", "de": "und", "es": "y", "fr": "et", "it": "e", "pt": "e"}
    date_title = {
        "en": "Published",
        "de": "Veröffentlicht",
        "es": "Publicado",
        "fr": "Publié",
        "it": "Pubblicato",
        "pt": "Publicados",
    }
    keywords_title = {
        "en": "Keywords",
        "de": "Schlüsselwörter",
        "es": "Palabras clave",
        "fr": "Mots clés",
        "it": "Parole chiave",
        "pt": "Palavras-chave",
    }
    citation_title = {
        "en": "Citation",
        "de": "Zitiervorschlag",
        "es": "Cita",
        "fr": "Citation",
        "it": "Citazione",
        "pt": "Citação",
    }
    copyright_title = {
        "en": "Copyright",
        "de": "Urheberrecht",
        "es": "Copyright",
        "fr": "Droit d'auteur",
        "it": "Copyright",
        "pt": "Direitos de autor",
    }
    lang = markdown.get("lang", "en")
    markdown["lastsep"] = lastsep.get(lang, "and")
    markdown["date-title"] = date_title.get(lang, "Published")
    markdown["keywords-title"] = keywords_title.get(lang, "Keywords")
    markdown["citation-title"] = citation_title.get(lang, "Citation")
    markdown["copyright-title"] = copyright_title.get(lang, "Copyright")
    return markdown


def id_as_str(id: str) -> Optional[str]:
    """Get id as string, strip scheme and doi.org host"""
    if id is None:
        return None
    u = furl(id)
    if u.host == "doi.org":
        return str(u.path).lstrip("/")
    if u.host != "":
        return u.host + str(u.path)
    return None


# supported accept headers for content negotiation
SUPPORTED_ACCEPT_HEADERS = [
    "application/vnd.commonmeta+json",
    "application/x-bibtex",
    "application/x-research-info-systems",
    "application/vnd.citationstyles.csl+json",
    "application/vnd.schemaorg.ld+json",
    "application/vnd.datacite.datacite+json",
    "application/vnd.crossref.unixref+xml",
    "text/x-bibliography",
]


async def get_single_work(string: str) -> Optional[dict]:
    """Get single work from in commonmeta format."""
    
    try:
        subject = Metadata(string)
        return JSON.loads(subject.write(to="commonmeta"))
    except Exception as exc:
        print(exc)
        return None


def get_formatted_work(
    subject, accept_header: str, style: str = "apa", locale: str = "en-US"
):
    """Get formatted work."""
    accept_headers = {
        "application/vnd.commonmeta+json": "commonmeta",
        "application/x-bibtex": "bibtex",
        "application/x-research-info-systems": "ris",
        "application/vnd.citationstyles.csl+json": "csl",
        "application/vnd.schemaorg.ld+json": "schema_org",
        "application/vnd.datacite.datacite+json": "datacite",
        "application/vnd.crossref.unixref+xml": "crossref_xml",
        "text/x-bibliography": "citation",
    }
    content_type = accept_headers.get(accept_header, "commonmeta")
    if content_type == "citation":
        # workaround for properly formatting blog posts
        subject.type = "JournalArticle"
        return subject.write(to="citation", style=style, locale=locale)
    else:
        return subject.write(to=content_type)


async def format_reference(url, index=0, extract_references: bool = False):
    """Format reference."""
    if validate_url(normalize_id(url)) == "DOI" and extract_references:
        id_ = normalize_id(url)
        subject = Metadata(id_)        
        if subject is not {}:
            # remove publisher field for articles, workaround for unstructured citation
            if subject.type == "Article":
                subject.publisher = None

            identifier = subject.id
            title = py_.get(subject, "titles[0].title")
            publication_year = py_.get(subject, "date.published")
            if publication_year is not None:
                publication_year = publication_year[:4]
            unstructured = subject.write(to="citation", style="apa", locale="en-US")
            
            # remove HTML tags such as <i> and <sup> from unstructured citation
            tags = nh3.ALLOWED_TAGS - {"b", "i", "sup", "sub"}
            unstructured = nh3.clean(unstructured, tags=tags)
        else:
            identifier = id_
            title = None
            publication_year = None
        return compact(
            {
                "key": f"ref{index + 1}",
                "id": identifier,
                "title": title,
                "publicationYear": publication_year[:4] if publication_year else None,
                "unstructured": unstructured,
            }
        )
    else:
        return {
            "key": f"ref{index + 1}",
            "id": url,
        }
