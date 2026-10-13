"""Lista la última búsqueda guardada."""

from db.session import session_factory
from search.store import format_last, latest_done


def main() -> None:
    factory = session_factory()
    with factory() as session:
        print(format_last(latest_done(session)))


if __name__ == "__main__":
    main()
