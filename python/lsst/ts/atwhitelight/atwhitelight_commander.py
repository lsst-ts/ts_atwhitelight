__all__ = ["command_atwhitelight"]

import asyncio

from lsst.ts import salobj

# something working


class ATWhiteLightCommander(salobj.CscCommander):
    """ATWhiteLight commander.

    Parameters
    ----------
    enable : bool
        Enable the CSC when first connecting to it?
    """

    def __init__(self, enable):
        super().__init__(
            name="ATWhiteLight",
            index=0,
            enable=enable,
            telemetry_fields_to_not_compare=("returnTemperature",),
        )


def command_atwhitelight() -> None:
    """Run the ATWhiteLight commander."""
    asyncio.run(ATWhiteLightCommander.amain(index=None))
