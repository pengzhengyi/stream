"""Run a plugin host, or with `job` a Job process: `python -m medleyplay.plugin_host [job]`.

The server starts both; neither is run by hand.
"""

import sys

if sys.argv[1:] == ["job"]:
    from medleyplay.plugin_host.job import main
else:
    from medleyplay.plugin_host.host import main

raise SystemExit(main())
