"""CleanData Studio backend."""

import pandas as pd

# Copy-on-write lets each cleaning step share unchanged columns with the previous
# version instead of copying the whole table. It is always on in pandas 3; on
# pandas 2.x it must be enabled explicitly.
if int(pd.__version__.split(".")[0]) < 3:
    pd.set_option("mode.copy_on_write", True)
