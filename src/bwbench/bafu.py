"""The BAFU 2025 database as a ``System``: a second real case, at a tenth of ecoinvent's size and above.

The Life Cycle Inventory database of the Swiss Federal Administration (BAFU:2025), by the
Federal Office for the Environment (FOEN): 11,747 processes. Brightway's file server hosts it as
the project archive that ``bw2io.install_project("BAFU-2025-v2")`` downloads, read here as
``bwbench.useeio`` reads USEEIO's: the processed datapackages, renumbered, values unchanged.

FOEN's terms allow its use in LCA studies but not its distribution, alone or inside another
database. So the archive is fetched at run time into the cache, never into this repository or
a published dataset, and only timings and aggregate statistics leave the machine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bwbench import useeio

if TYPE_CHECKING:
    from bwbench.synth import Profile, System

# shortcut: pinned by hand, like useeio.URL. Move to sourceledger with it.
URL = "https://files.brightway.dev/bafu-2025-v2.tar.gz"
SHA256 = "54cb370abba22ad1f6a9f6f9ef65f9fbad5a496fdf785cd5ad9517701b47a38e"
# EN 15804+A2 climate change, acidification and freshwater ecotoxicity: 45, 6 and 1,373 factors.
METHODS = tuple(
    f"EN_15804_A2_Method_{category}" for category in ("Climate_change", "Acidification", "Ecotoxicity_freshwater")
)


def system(p: Profile, seed: int) -> System:
    """The BAFU 2025 system of profile ``p``, fetched into the cache on first use."""
    from bwbench.synth import data_root  # noqa: PLC0415 - synth imports this module

    archive = useeio.fetch(data_root() / "bafu-2025-v2.tar.gz", URL, SHA256)
    return useeio.archive_system("bafu", p, seed, archive, METHODS)
