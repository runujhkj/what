from ..log_view import print_history, print_last, print_log_by_id


def handle_log(args) -> None:
    if args.history:
        print_history(args.history)
        return
    if args.last:
        print_last()
        return
    if args.id is not None:
        print_log_by_id(args.id)
        return
    print("use --history N, --last, or --id")
