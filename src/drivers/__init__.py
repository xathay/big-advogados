"""big-drivers — instalacao curada de drivers proprietarios PKCS#11.

Cada driver e descrito por um arquivo TOML em data/drivers/. O modulo
baixa do canal oficial do fabricante (ou distribuidor licenciado),
verifica SHA-256, mostra a EULA original ao usuario e, apos aceite,
delega a instalacao a um helper privilegiado isolado.

Sem AUR, sem reempacotamento comunitario, sem terminal escondendo
prompts. A meta e que o usuario sempre veja exatamente o que esta
sendo baixado, de onde, e sob que licenca.
"""
from src.drivers.catalog import DriverCatalog
from src.drivers.installer import DriverInstaller, InstallProgress, InstallStage
from src.drivers.types import DriverSpec, TokenMatch

__all__ = [
    "DriverCatalog",
    "DriverInstaller",
    "DriverSpec",
    "InstallProgress",
    "InstallStage",
    "TokenMatch",
]
