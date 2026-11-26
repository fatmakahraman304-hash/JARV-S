"""Write the complete local catalog to stdout as CSV with python -m tools.capability_inventory."""
import csv
import sys

from core import thinking_studio as studio


def write_inventory(stream):
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(("Numara", "Yetenek", "Sınıf", "Çalışma kapsamı", "Yerel işlem"))
    for n, (title, _) in sorted(studio.FEATURES.items()):
        writer.writerow((n, title, studio.implementation_kind(n), studio.feature_status(n),
                         studio.UTILITY_BINDINGS.get(n, "")))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", newline="")
    write_inventory(sys.stdout)
