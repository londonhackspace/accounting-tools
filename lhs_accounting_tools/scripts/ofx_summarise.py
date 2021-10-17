from ofxtools.Parser import OFXTree
from ofxtools.models import (
    STMTTRN,
    STATUS,
    OFX,
    SONRS,
    BANKMSGSRSV1,
    STMTTRNRS,
    SIGNONMSGSRSV1,
    STMTRS,
    BANKTRANLIST,
)
from ofxtools.Types import OFXTypeWarning
from ofxtools.header import make_header
from more_itertools import chunked
from pathlib import Path
from datetime import datetime
import xml.etree.ElementTree as ET
import click
import re
import pytz
import warnings

# Suppress warning about OFX descriptions longer than the spec allows.
warnings.filterwarnings("ignore", category=OFXTypeWarning)


@click.command()
@click.option(
    "--min-sub", default=5, help="Minimum subscription amount (£)", show_default=True
)
@click.option(
    "--max-output-size",
    default=200,
    help="Maximum number of transactions in a single output file",
    show_default=True,
)
@click.option(
    "--since-date",
    type=click.DateTime(),
    help="Only emit transactions after this date (Membership payments before this date are still counted.)",
)
@click.argument("input_ofx", type=click.File("rb"))
@click.argument("output_dir", type=click.Path(path_type=Path))
def main(min_sub, max_output_size, since_date, input_ofx, output_dir):
    """
    Summarise London Hackspace bank statements before reconciliation.

    This tool takes an input OFX file (INPUT_OFX) and combines all subscription
    payment transactions which have a reference matching the correct format. A pair of
    transactions are produced at the end of each calendar month - one for subscriptions
    (up to the minimum payment), and one for donations (above the minimum payment).

    The result is written as a series of OFX files to OUTPUT_DIR.
    """

    output_dir = output_dir.resolve()
    output_dir.mkdir(exist_ok=True)

    since_date = since_date.replace(tzinfo=pytz.UTC)

    if len(list(output_dir.glob("*.ofx"))) > 0:
        click.secho(
            f"OFX files already exist in the output directory ({output_dir}). Aborting to avoid confusion.",
            fg="red",
        )
        return 1

    click.secho("Parsing...", fg="blue")
    parser = OFXTree()
    parser.parse(input_ofx)
    ofx = parser.convert()
    click.secho("Processing...", fg="blue")
    assert len(ofx.statements) == 1, "Unexpected number of statement entities"

    files_written = 0
    for chunk in chunked(
        filter_date(
            summarise_transactions(ofx.statements[0].banktranlist, min_sub), since_date
        ),
        max_output_size,
    ):
        chunk = list(chunk)
        output_file = output_dir / chunk[0].dtposted.strftime("%Y-%m-%d.ofx")

        out_ofx = generate_ofx(chunk, ofx)
        et = out_ofx.to_etree()
        with output_file.open("wb") as f:
            f.write(str(make_header(version=220)).encode("utf-8"))
            f.write(ET.tostring(et))

        files_written += 1
    click.secho(
        f"Complete. Wrote {files_written} output file(s) to {output_dir}.", fg="blue"
    )


def filter_date(transactions, since_date):
    if since_date is None:
        yield from transactions
        return

    for t in transactions:
        if t.dtposted <= since_date:
            continue
        yield t


def summarise_transactions(transactions: list[STMTTRN], min_sub):
    """
    Given a list of transactions (ofxtools STMTTRN objects), summarise them by
    combining the subscription transactions together.

    Returns a generator yielding the resulting STMTTRN objects.
    """
    sub_sum = donate_sum = count = 0
    last_date = None
    first_month_passed = False  # Whether we've seen at least a month of transactions

    for t in sorted(transactions, key=lambda t: t.dtposted):
        if int(t.fitid) < 200900000000000:
            # Barclays temporary transaction ID used for uncleared transactions
            # (maybe historical)
            continue

        if (
            last_date is not None
            and last_date.month != t.dtposted.month
            and sub_sum > 0
        ):
            # Month end has passed - last_date is the last transaction from the previous month.
            # Check if we should generate a summary.
            if first_month_passed:
                click.secho(
                    f"Generated summary transactions for {last_date.year}-{last_date.month} "
                    f"({count} payments)",
                    fg="green",
                )

                yield STMTTRN(
                    fitid=f"SUBSUMMARY{last_date.year}{last_date.month}",
                    trntype="OTHER",
                    dtposted=last_date,
                    name=f"Bank transfer subscriptions for {last_date.year}-{last_date.month} ({count} payments)",
                    trnamt=sub_sum,
                )
                yield STMTTRN(
                    fitid=f"DONATESUMMARY{last_date.year}{last_date.month}",
                    trntype="OTHER",
                    dtposted=last_date,
                    name=f"Bank transfer donations for {last_date.year}-{last_date.month} ({count} payments)",
                    trnamt=donate_sum,
                )
            else:
                # Don't generate a summary for less than a full month of subscriptions.
                click.secho(
                    f"Generating summary transactions starting from {t.dtposted.year}-{t.dtposted.month}...",
                    fg="blue",
                )

            sub_sum = donate_sum = count = 0
            first_month_passed = True

        amount = t.trnamt
        if re.search(r"H[S5] ?([O0-9]{4,})", t.name, flags=re.I):
            if amount >= min_sub:
                sub_sum += min_sub
                donate_sum += amount - min_sub
            else:
                # Payment below the subscription threshold - 100% donation.
                donate_sum += amount

            count += 1
        else:
            # Not a subscription transaction, return it unchanged.
            yield t

        last_date = t.dtposted


def generate_ofx(transactions, source_ofx):
    """Generate the ofxtools OFX structure for the output files.
    This is all just annoying boilerplate.
    """
    status_ok = STATUS(code=0, severity="INFO")
    ofx = OFX(
        signonmsgsrsv1=SIGNONMSGSRSV1(
            sonrs=SONRS(
                status=status_ok, dtserver=datetime.now(tz=pytz.utc), language="ENG"
            )
        ),
        bankmsgsrsv1=BANKMSGSRSV1(
            STMTTRNRS(
                trnuid="1",
                status=status_ok,
                stmtrs=STMTRS(
                    curdef="GBP",
                    bankacctfrom=source_ofx.statements[0].bankacctfrom,
                    ledgerbal=source_ofx.statements[0].ledgerbal,
                    banktranlist=BANKTRANLIST(
                        *transactions,
                        dtstart=transactions[0].dtposted,
                        dtend=transactions[-1].dtposted,
                    ),
                ),
            )
        ),
    )

    return ofx


if __name__ == "__main__":
    main()
