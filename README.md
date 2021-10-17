# London Hackspace Accounting Tools

This repository contains tools for pre-processing and importing accounting data into Xero for London Hackspace.

## Installation

Install directly from GitHub using pip:

	pip install git+https://github.com/londonhackspace/accounting-tools#egg=lhs-accounting-tools

This should install the tools into your PATH:

## lhs-ofx-summarise
```
Usage: lhs-ofx-summarise [OPTIONS] INPUT_OFX OUTPUT_DIR

  Summarise London Hackspace bank statements before reconciliation.

  This tool takes an input OFX file (INPUT_OFX) and combines all subscription
  payment transactions which have a reference matching the correct format. A
  pair of transactions are produced at the end of each calendar month - one
  for subscriptions (up to the minimum payment), and one for donations (above
  the minimum payment).

  The result is written as a series of OFX files to OUTPUT_DIR.

Options:
  --min-sub INTEGER               Minimum subscription amount (£)  [default:
                                  5]
  --max-output-size INTEGER       Maximum number of transactions in a single
                                  output file  [default: 200]
  --since-date [%Y-%m-%d|%Y-%m-%dT%H:%M:%S|%Y-%m-%d %H:%M:%S]
                                  Only emit transactions after this date
                                  (Membership payments before this date are
                                  still counted.)
  --help                          Show this message and exit.
```

## lhs-gocardless-journals
```
Usage: lhs-gocardless-journals [OPTIONS] OUTPUT_CSV

  Fetch transactions from the GoCardless API and emit a CSV file of manual
  journals (one per month) for import into Xero.

Options:
  --from-date [%Y-%m-%d]    Date to start fetching transactions from
                            (inclusive)  [required]
  --until-date [%Y-%m-%d]   Date to fetch transactions until (inclusive)
                            [required]
  --min-membership INTEGER  Mandatory minimum membership fee (£)  [default: 5]
  --access-token TEXT       GoCardless API read only access token (can also be
                            provided through the GOCARDLESS_ACCESS_TOKEN
                            environment variable).  [required]
  --help                    Show this message and exit.
```
