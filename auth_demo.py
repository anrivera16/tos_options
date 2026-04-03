import sys

from cli import main


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv.extend(["auth"])
    main()
