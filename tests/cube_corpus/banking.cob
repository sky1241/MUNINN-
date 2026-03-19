       IDENTIFICATION DIVISION.
       PROGRAM-ID. BANKING-TRANSACTION-SYSTEM.
       AUTHOR. LEGACY-BANKING-TEAM.
       DATE-WRITTEN. 1987-03-15.
       DATE-COMPILED.
      *================================================================*
      * BANKING TRANSACTION PROCESSING SYSTEM                          *
      * Handles deposits, withdrawals, transfers, balance inquiries    *
      * Batch processing with sequential master file update            *
      * Daily reconciliation and audit trail generation                *
      *================================================================*
       ENVIRONMENT DIVISION.
       CONFIGURATION SECTION.
       SOURCE-COMPUTER. IBM-3090.
       OBJECT-COMPUTER. IBM-3090.
       SPECIAL-NAMES.
           DECIMAL-POINT IS COMMA.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT MASTER-FILE
               ASSIGN TO 'ACCTMAST'
               ORGANIZATION IS INDEXED
               ACCESS MODE IS DYNAMIC
               RECORD KEY IS WS-ACCT-NUMBER
               ALTERNATE RECORD KEY IS WS-CUSTOMER-NAME
                   WITH DUPLICATES
               FILE STATUS IS WS-MASTER-STATUS.
           SELECT TRANSACTION-FILE
               ASSIGN TO 'TRANFILE'
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE IS SEQUENTIAL
               FILE STATUS IS WS-TRANS-STATUS.
           SELECT REPORT-FILE
               ASSIGN TO 'RPTFILE'
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE IS SEQUENTIAL
               FILE STATUS IS WS-REPORT-STATUS.
           SELECT AUDIT-FILE
               ASSIGN TO 'AUDFILE'
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE IS SEQUENTIAL
               FILE STATUS IS WS-AUDIT-STATUS.
           SELECT ERROR-FILE
               ASSIGN TO 'ERRFILE'
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE IS SEQUENTIAL
               FILE STATUS IS WS-ERROR-STATUS.
           SELECT RECONCILIATION-FILE
               ASSIGN TO 'RECFILE'
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE IS SEQUENTIAL
               FILE STATUS IS WS-RECON-STATUS.

       DATA DIVISION.
       FILE SECTION.
      *================================================================*
      * MASTER ACCOUNT FILE                                            *
      *================================================================*
       FD  MASTER-FILE
           LABEL RECORDS ARE STANDARD
           BLOCK CONTAINS 0 RECORDS
           RECORD CONTAINS 500 CHARACTERS.
       01  MASTER-RECORD.
           05  WS-ACCT-NUMBER          PIC 9(10).
           05  WS-CUSTOMER-NAME        PIC X(40).
           05  WS-CUSTOMER-ADDRESS.
               10  WS-ADDR-LINE-1      PIC X(30).
               10  WS-ADDR-LINE-2      PIC X(30).
               10  WS-ADDR-CITY        PIC X(20).
               10  WS-ADDR-STATE       PIC X(2).
               10  WS-ADDR-ZIP         PIC 9(5).
           05  WS-ACCOUNT-TYPE         PIC X(2).
               88  ACCT-CHECKING       VALUE 'CH'.
               88  ACCT-SAVINGS        VALUE 'SA'.
               88  ACCT-MONEY-MARKET   VALUE 'MM'.
               88  ACCT-CERTIFICATE    VALUE 'CD'.
               88  ACCT-LOAN           VALUE 'LN'.
           05  WS-ACCOUNT-STATUS       PIC X(1).
               88  ACCT-ACTIVE         VALUE 'A'.
               88  ACCT-FROZEN         VALUE 'F'.
               88  ACCT-CLOSED         VALUE 'C'.
               88  ACCT-DORMANT        VALUE 'D'.
           05  WS-BALANCE              PIC S9(11)V99 COMP-3.
           05  WS-AVAILABLE-BALANCE    PIC S9(11)V99 COMP-3.
           05  WS-HOLD-AMOUNT          PIC S9(9)V99 COMP-3.
           05  WS-INTEREST-RATE        PIC 9V9(4) COMP-3.
           05  WS-INTEREST-ACCRUED     PIC S9(9)V99 COMP-3.
           05  WS-LAST-ACTIVITY-DATE   PIC 9(8).
           05  WS-OPEN-DATE            PIC 9(8).
           05  WS-CUSTOMER-SSN         PIC 9(9).
           05  WS-OVERDRAFT-LIMIT      PIC S9(7)V99 COMP-3.
           05  WS-DAILY-WITHDRAWAL-AMT PIC S9(7)V99 COMP-3.
           05  WS-DAILY-WITHDRAWAL-CNT PIC 9(3) COMP-3.
           05  WS-MONTHLY-FEE          PIC S9(5)V99 COMP-3.
           05  WS-MIN-BALANCE          PIC S9(9)V99 COMP-3.
           05  WS-STATEMENT-CYCLE      PIC 9(2).
           05  WS-BRANCH-CODE          PIC 9(4).
           05  WS-OFFICER-CODE         PIC X(6).
           05  WS-TAX-ID-TYPE          PIC X(1).
               88  TAX-SSN             VALUE 'S'.
               88  TAX-EIN             VALUE 'E'.
               88  TAX-ITIN            VALUE 'I'.
           05  WS-SIGNATURE-CARD       PIC X(1).
               88  SIG-ON-FILE         VALUE 'Y'.
               88  SIG-NOT-ON-FILE     VALUE 'N'.
           05  WS-FILLER-MASTER        PIC X(246).

      *================================================================*
      * TRANSACTION INPUT FILE                                         *
      *================================================================*
       FD  TRANSACTION-FILE
           LABEL RECORDS ARE STANDARD
           BLOCK CONTAINS 0 RECORDS
           RECORD CONTAINS 200 CHARACTERS.
       01  TRANSACTION-RECORD.
           05  TR-ACCT-NUMBER          PIC 9(10).
           05  TR-TRANS-CODE           PIC X(2).
               88  TR-DEPOSIT          VALUE 'DP'.
               88  TR-WITHDRAWAL       VALUE 'WD'.
               88  TR-TRANSFER-OUT     VALUE 'TO'.
               88  TR-TRANSFER-IN      VALUE 'TI'.
               88  TR-PAYMENT          VALUE 'PM'.
               88  TR-FEE-CHARGE       VALUE 'FC'.
               88  TR-INTEREST-CREDIT  VALUE 'IC'.
               88  TR-ADJUSTMENT       VALUE 'AJ'.
               88  TR-BALANCE-INQUIRY  VALUE 'BI'.
               88  TR-ACCOUNT-CLOSE    VALUE 'CL'.
           05  TR-AMOUNT               PIC S9(9)V99 COMP-3.
           05  TR-TRANS-DATE           PIC 9(8).
           05  TR-TRANS-TIME           PIC 9(6).
           05  TR-BRANCH-CODE          PIC 9(4).
           05  TR-TELLER-ID            PIC X(6).
           05  TR-REFERENCE-NUM        PIC X(12).
           05  TR-TARGET-ACCT          PIC 9(10).
           05  TR-DESCRIPTION          PIC X(40).
           05  TR-CHECK-NUMBER         PIC 9(8).
           05  TR-AUTHORIZATION        PIC X(8).
           05  TR-SOURCE-CODE          PIC X(2).
               88  SRC-TELLER          VALUE 'TL'.
               88  SRC-ATM             VALUE 'AT'.
               88  SRC-ONLINE          VALUE 'OL'.
               88  SRC-MOBILE          VALUE 'MB'.
               88  SRC-ACH             VALUE 'AC'.
               88  SRC-WIRE            VALUE 'WR'.
               88  SRC-BATCH           VALUE 'BT'.
           05  TR-FILLER-TRANS         PIC X(72).

      *================================================================*
      * REPORT OUTPUT FILE                                             *
      *================================================================*
       FD  REPORT-FILE
           LABEL RECORDS ARE STANDARD
           RECORD CONTAINS 132 CHARACTERS.
       01  REPORT-RECORD              PIC X(132).

      *================================================================*
      * AUDIT TRAIL FILE                                               *
      *================================================================*
       FD  AUDIT-FILE
           LABEL RECORDS ARE STANDARD
           RECORD CONTAINS 300 CHARACTERS.
       01  AUDIT-RECORD.
           05  AU-TIMESTAMP            PIC 9(14).
           05  AU-ACCT-NUMBER          PIC 9(10).
           05  AU-TRANS-CODE           PIC X(2).
           05  AU-AMOUNT               PIC S9(9)V99 COMP-3.
           05  AU-BALANCE-BEFORE       PIC S9(11)V99 COMP-3.
           05  AU-BALANCE-AFTER        PIC S9(11)V99 COMP-3.
           05  AU-STATUS-CODE          PIC X(2).
               88  AU-SUCCESS          VALUE 'OK'.
               88  AU-INSUFFICIENT     VALUE 'IF'.
               88  AU-FROZEN           VALUE 'FZ'.
               88  AU-LIMIT-EXCEEDED   VALUE 'LE'.
               88  AU-INVALID-ACCT     VALUE 'IA'.
               88  AU-SYSTEM-ERROR     VALUE 'SE'.
           05  AU-TELLER-ID            PIC X(6).
           05  AU-BRANCH-CODE          PIC 9(4).
           05  AU-REFERENCE            PIC X(12).
           05  AU-DESCRIPTION          PIC X(60).
           05  AU-FILLER-AUDIT         PIC X(169).

      *================================================================*
      * ERROR FILE                                                     *
      *================================================================*
       FD  ERROR-FILE
           LABEL RECORDS ARE STANDARD
           RECORD CONTAINS 200 CHARACTERS.
       01  ERROR-RECORD.
           05  ER-TIMESTAMP            PIC 9(14).
           05  ER-ACCT-NUMBER          PIC 9(10).
           05  ER-TRANS-CODE           PIC X(2).
           05  ER-ERROR-CODE           PIC X(4).
           05  ER-ERROR-MESSAGE        PIC X(80).
           05  ER-FILLER-ERROR         PIC X(90).

      *================================================================*
      * RECONCILIATION FILE                                            *
      *================================================================*
       FD  RECONCILIATION-FILE
           LABEL RECORDS ARE STANDARD
           RECORD CONTAINS 132 CHARACTERS.
       01  RECON-RECORD               PIC X(132).

       WORKING-STORAGE SECTION.
      *================================================================*
      * FILE STATUS CODES                                              *
      *================================================================*
       01  WS-FILE-STATUSES.
           05  WS-MASTER-STATUS        PIC X(2).
               88  MASTER-OK           VALUE '00'.
               88  MASTER-DUP          VALUE '22'.
               88  MASTER-NOT-FOUND    VALUE '23'.
               88  MASTER-EOF          VALUE '10'.
           05  WS-TRANS-STATUS         PIC X(2).
               88  TRANS-OK            VALUE '00'.
               88  TRANS-EOF           VALUE '10'.
           05  WS-REPORT-STATUS        PIC X(2).
               88  REPORT-OK           VALUE '00'.
           05  WS-AUDIT-STATUS         PIC X(2).
               88  AUDIT-OK            VALUE '00'.
           05  WS-ERROR-STATUS         PIC X(2).
               88  ERROR-OK            VALUE '00'.
           05  WS-RECON-STATUS         PIC X(2).
               88  RECON-OK            VALUE '00'.

      *================================================================*
      * WORKING VARIABLES                                              *
      *================================================================*
       01  WS-SWITCHES.
           05  WS-END-OF-TRANS         PIC X(1) VALUE 'N'.
               88  END-OF-TRANS        VALUE 'Y'.
               88  NOT-END-OF-TRANS    VALUE 'N'.
           05  WS-ACCT-FOUND           PIC X(1) VALUE 'N'.
               88  ACCT-FOUND          VALUE 'Y'.
               88  ACCT-NOT-FOUND      VALUE 'N'.
           05  WS-VALID-TRANS          PIC X(1) VALUE 'N'.
               88  VALID-TRANS         VALUE 'Y'.
               88  INVALID-TRANS       VALUE 'N'.
           05  WS-PROCESSING-ERROR     PIC X(1) VALUE 'N'.
               88  PROCESSING-ERROR    VALUE 'Y'.
               88  NO-PROCESSING-ERROR VALUE 'N'.

       01  WS-COUNTERS.
           05  WS-TRANS-READ           PIC 9(7) VALUE ZEROS.
           05  WS-TRANS-PROCESSED      PIC 9(7) VALUE ZEROS.
           05  WS-TRANS-REJECTED       PIC 9(7) VALUE ZEROS.
           05  WS-DEPOSIT-COUNT        PIC 9(7) VALUE ZEROS.
           05  WS-WITHDRAWAL-COUNT     PIC 9(7) VALUE ZEROS.
           05  WS-TRANSFER-COUNT       PIC 9(7) VALUE ZEROS.
           05  WS-INQUIRY-COUNT        PIC 9(7) VALUE ZEROS.
           05  WS-ERROR-COUNT          PIC 9(7) VALUE ZEROS.
           05  WS-PAGES-PRINTED        PIC 9(5) VALUE ZEROS.
           05  WS-LINES-PRINTED        PIC 9(3) VALUE ZEROS.

       01  WS-TOTALS.
           05  WS-TOTAL-DEPOSITS       PIC S9(13)V99 COMP-3
                                       VALUE ZEROS.
           05  WS-TOTAL-WITHDRAWALS    PIC S9(13)V99 COMP-3
                                       VALUE ZEROS.
           05  WS-TOTAL-TRANSFERS      PIC S9(13)V99 COMP-3
                                       VALUE ZEROS.
           05  WS-TOTAL-FEES           PIC S9(11)V99 COMP-3
                                       VALUE ZEROS.
           05  WS-TOTAL-INTEREST       PIC S9(11)V99 COMP-3
                                       VALUE ZEROS.
           05  WS-NET-ACTIVITY         PIC S9(13)V99 COMP-3
                                       VALUE ZEROS.

       01  WS-LIMITS.
           05  WS-MAX-DAILY-WD         PIC S9(7)V99 COMP-3
                                       VALUE 10000.00.
           05  WS-MAX-DAILY-WD-COUNT   PIC 9(3) VALUE 010.
           05  WS-MAX-TRANSFER-AMT     PIC S9(9)V99 COMP-3
                                       VALUE 250000.00.
           05  WS-MIN-BALANCE-CHK      PIC S9(7)V99 COMP-3
                                       VALUE 100.00.
           05  WS-MIN-BALANCE-SAV      PIC S9(7)V99 COMP-3
                                       VALUE 25.00.
           05  WS-OVERDRAFT-FEE        PIC S9(5)V99 COMP-3
                                       VALUE 35.00.
           05  WS-DAILY-LIMIT-ATM      PIC S9(7)V99 COMP-3
                                       VALUE 500.00.
           05  WS-WIRE-FEE-DOMESTIC    PIC S9(5)V99 COMP-3
                                       VALUE 25.00.
           05  WS-WIRE-FEE-INTL        PIC S9(5)V99 COMP-3
                                       VALUE 45.00.

       01  WS-DATE-FIELDS.
           05  WS-CURRENT-DATE.
               10  WS-CURR-YEAR       PIC 9(4).
               10  WS-CURR-MONTH      PIC 9(2).
               10  WS-CURR-DAY        PIC 9(2).
           05  WS-CURRENT-TIME.
               10  WS-CURR-HOUR       PIC 9(2).
               10  WS-CURR-MIN        PIC 9(2).
               10  WS-CURR-SEC        PIC 9(2).
           05  WS-FORMATTED-DATE      PIC X(10).
           05  WS-FORMATTED-TIME      PIC X(8).
           05  WS-TIMESTAMP           PIC 9(14).

       01  WS-WORK-FIELDS.
           05  WS-WORK-AMOUNT         PIC S9(11)V99 COMP-3.
           05  WS-WORK-BALANCE        PIC S9(11)V99 COMP-3.
           05  WS-SAVE-BALANCE        PIC S9(11)V99 COMP-3.
           05  WS-INTEREST-CALC       PIC S9(11)V99 COMP-3.
           05  WS-DAILY-RATE          PIC 9V9(8) COMP-3.
           05  WS-DAYS-IN-PERIOD      PIC 9(3) COMP-3.
           05  WS-FEE-AMOUNT          PIC S9(5)V99 COMP-3.
           05  WS-DISPLAY-AMOUNT      PIC Z(10)9.99-.
           05  WS-DISPLAY-BALANCE     PIC Z(10)9.99-.
           05  WS-DISPLAY-ACCT        PIC 9(10).

      *================================================================*
      * REPORT LINES                                                   *
      *================================================================*
       01  WS-RPT-HEADER-1.
           05  FILLER                  PIC X(1) VALUE SPACES.
           05  FILLER                  PIC X(40)
               VALUE 'DAILY TRANSACTION PROCESSING REPORT     '.
           05  FILLER                  PIC X(20) VALUE SPACES.
           05  WS-RPT-DATE            PIC X(10).
           05  FILLER                  PIC X(5) VALUE SPACES.
           05  FILLER                  PIC X(5) VALUE 'PAGE '.
           05  WS-RPT-PAGE            PIC Z(4)9.
           05  FILLER                  PIC X(46) VALUE SPACES.

       01  WS-RPT-HEADER-2.
           05  FILLER                  PIC X(1) VALUE SPACES.
           05  FILLER                  PIC X(10)
               VALUE 'ACCOUNT   '.
           05  FILLER                  PIC X(5) VALUE SPACES.
           05  FILLER                  PIC X(6) VALUE 'TYPE  '.
           05  FILLER                  PIC X(5) VALUE SPACES.
           05  FILLER                  PIC X(15)
               VALUE 'AMOUNT         '.
           05  FILLER                  PIC X(5) VALUE SPACES.
           05  FILLER                  PIC X(15)
               VALUE 'BALANCE        '.
           05  FILLER                  PIC X(5) VALUE SPACES.
           05  FILLER                  PIC X(8) VALUE 'STATUS  '.
           05  FILLER                  PIC X(5) VALUE SPACES.
           05  FILLER                  PIC X(12)
               VALUE 'REFERENCE   '.
           05  FILLER                  PIC X(40) VALUE SPACES.

       01  WS-RPT-DETAIL.
           05  FILLER                  PIC X(1) VALUE SPACES.
           05  WS-RPT-ACCT            PIC 9(10).
           05  FILLER                  PIC X(5) VALUE SPACES.
           05  WS-RPT-TYPE            PIC X(6).
           05  FILLER                  PIC X(5) VALUE SPACES.
           05  WS-RPT-AMOUNT          PIC Z(10)9.99-.
           05  FILLER                  PIC X(1) VALUE SPACES.
           05  WS-RPT-BALANCE         PIC Z(10)9.99-.
           05  FILLER                  PIC X(5) VALUE SPACES.
           05  WS-RPT-STATUS          PIC X(8).
           05  FILLER                  PIC X(5) VALUE SPACES.
           05  WS-RPT-REF             PIC X(12).
           05  FILLER                  PIC X(38) VALUE SPACES.

       01  WS-RPT-FOOTER.
           05  FILLER                  PIC X(1) VALUE SPACES.
           05  FILLER                  PIC X(30)
               VALUE '*** END OF REPORT ***         '.
           05  FILLER                  PIC X(101) VALUE SPACES.

       01  WS-RPT-SUMMARY-LINES.
           05  WS-RPT-SUM-1.
               10  FILLER             PIC X(30)
                   VALUE ' TRANSACTIONS READ:           '.
               10  WS-RPT-SUM-READ   PIC Z(6)9.
               10  FILLER             PIC X(95) VALUE SPACES.
           05  WS-RPT-SUM-2.
               10  FILLER             PIC X(30)
                   VALUE ' TRANSACTIONS PROCESSED:      '.
               10  WS-RPT-SUM-PROC   PIC Z(6)9.
               10  FILLER             PIC X(95) VALUE SPACES.
           05  WS-RPT-SUM-3.
               10  FILLER             PIC X(30)
                   VALUE ' TRANSACTIONS REJECTED:       '.
               10  WS-RPT-SUM-REJ    PIC Z(6)9.
               10  FILLER             PIC X(95) VALUE SPACES.
           05  WS-RPT-SUM-4.
               10  FILLER             PIC X(30)
                   VALUE ' TOTAL DEPOSITS:              '.
               10  WS-RPT-SUM-DEP    PIC Z(12)9.99-.
               10  FILLER             PIC X(85) VALUE SPACES.
           05  WS-RPT-SUM-5.
               10  FILLER             PIC X(30)
                   VALUE ' TOTAL WITHDRAWALS:           '.
               10  WS-RPT-SUM-WD     PIC Z(12)9.99-.
               10  FILLER             PIC X(85) VALUE SPACES.
           05  WS-RPT-SUM-6.
               10  FILLER             PIC X(30)
                   VALUE ' TOTAL TRANSFERS:             '.
               10  WS-RPT-SUM-XFR    PIC Z(12)9.99-.
               10  FILLER             PIC X(85) VALUE SPACES.
           05  WS-RPT-SUM-7.
               10  FILLER             PIC X(30)
                   VALUE ' NET ACTIVITY:                '.
               10  WS-RPT-SUM-NET    PIC Z(12)9.99-.
               10  FILLER             PIC X(85) VALUE SPACES.

      *================================================================*
      * RECONCILIATION WORK AREAS                                      *
      *================================================================*
       01  WS-RECON-WORK.
           05  WS-RECON-TOTAL-DEBITS  PIC S9(13)V99 COMP-3
                                      VALUE ZEROS.
           05  WS-RECON-TOTAL-CREDITS PIC S9(13)V99 COMP-3
                                      VALUE ZEROS.
           05  WS-RECON-DIFFERENCE    PIC S9(13)V99 COMP-3
                                      VALUE ZEROS.
           05  WS-RECON-STATUS        PIC X(10) VALUE SPACES.
           05  WS-RECON-OUT-OF-BAL    PIC X(1) VALUE 'N'.
               88  RECON-BALANCED     VALUE 'N'.
               88  RECON-OUT-OF-BAL   VALUE 'Y'.

      *================================================================*
      * INTEREST CALCULATION WORK AREAS                                *
      *================================================================*
       01  WS-INTEREST-WORK.
           05  WS-INT-ANNUAL-RATE     PIC 9V9(4) COMP-3.
           05  WS-INT-DAILY-RATE      PIC 9V9(8) COMP-3.
           05  WS-INT-DAYS            PIC 9(3) COMP-3.
           05  WS-INT-PRINCIPAL       PIC S9(11)V99 COMP-3.
           05  WS-INT-EARNED          PIC S9(9)V99 COMP-3.
           05  WS-INT-YTD             PIC S9(9)V99 COMP-3.

       PROCEDURE DIVISION.
      *================================================================*
      * MAIN PROCESSING CONTROL                                        *
      *================================================================*
       0000-MAIN-CONTROL.
           PERFORM 1000-INITIALIZE
           PERFORM 2000-PROCESS-TRANSACTIONS
               UNTIL END-OF-TRANS
           PERFORM 8000-RECONCILIATION
           PERFORM 9000-FINALIZE
           STOP RUN.

      *================================================================*
      * INITIALIZATION                                                 *
      *================================================================*
       1000-INITIALIZE.
           PERFORM 1100-OPEN-FILES
           PERFORM 1200-GET-DATE-TIME
           PERFORM 1300-PRINT-HEADERS
           PERFORM 1400-READ-TRANSACTION.

       1100-OPEN-FILES.
           OPEN I-O    MASTER-FILE
           IF NOT MASTER-OK
               DISPLAY 'ERROR OPENING MASTER FILE: ' WS-MASTER-STATUS
               PERFORM 9999-ABEND-ROUTINE
           END-IF

           OPEN INPUT  TRANSACTION-FILE
           IF NOT TRANS-OK
               DISPLAY 'ERROR OPENING TRANSACTION FILE: '
                       WS-TRANS-STATUS
               PERFORM 9999-ABEND-ROUTINE
           END-IF

           OPEN OUTPUT REPORT-FILE
           IF NOT REPORT-OK
               DISPLAY 'ERROR OPENING REPORT FILE: '
                       WS-REPORT-STATUS
               PERFORM 9999-ABEND-ROUTINE
           END-IF

           OPEN OUTPUT AUDIT-FILE
           IF NOT AUDIT-OK
               DISPLAY 'ERROR OPENING AUDIT FILE: '
                       WS-AUDIT-STATUS
               PERFORM 9999-ABEND-ROUTINE
           END-IF

           OPEN OUTPUT ERROR-FILE
           IF NOT ERROR-OK
               DISPLAY 'ERROR OPENING ERROR FILE: '
                       WS-ERROR-STATUS
               PERFORM 9999-ABEND-ROUTINE
           END-IF

           OPEN OUTPUT RECONCILIATION-FILE
           IF NOT RECON-OK
               DISPLAY 'ERROR OPENING RECON FILE: '
                       WS-RECON-STATUS
               PERFORM 9999-ABEND-ROUTINE
           END-IF.

       1200-GET-DATE-TIME.
           ACCEPT WS-CURRENT-DATE FROM DATE YYYYMMDD
           ACCEPT WS-CURRENT-TIME FROM TIME

           STRING WS-CURR-YEAR   DELIMITED BY SIZE
                  '-'             DELIMITED BY SIZE
                  WS-CURR-MONTH  DELIMITED BY SIZE
                  '-'             DELIMITED BY SIZE
                  WS-CURR-DAY    DELIMITED BY SIZE
               INTO WS-FORMATTED-DATE
           END-STRING

           STRING WS-CURR-HOUR   DELIMITED BY SIZE
                  ':'             DELIMITED BY SIZE
                  WS-CURR-MIN    DELIMITED BY SIZE
                  ':'             DELIMITED BY SIZE
                  WS-CURR-SEC    DELIMITED BY SIZE
               INTO WS-FORMATTED-TIME
           END-STRING

           STRING WS-CURRENT-DATE DELIMITED BY SIZE
                  WS-CURRENT-TIME DELIMITED BY SIZE
               INTO WS-TIMESTAMP
           END-STRING.

       1300-PRINT-HEADERS.
           MOVE WS-FORMATTED-DATE TO WS-RPT-DATE
           ADD 1 TO WS-PAGES-PRINTED
           MOVE WS-PAGES-PRINTED TO WS-RPT-PAGE
           WRITE REPORT-RECORD FROM WS-RPT-HEADER-1
               AFTER ADVANCING PAGE
           WRITE REPORT-RECORD FROM WS-RPT-HEADER-2
               AFTER ADVANCING 2 LINES
           MOVE SPACES TO REPORT-RECORD
           WRITE REPORT-RECORD
               AFTER ADVANCING 1 LINE
           MOVE 5 TO WS-LINES-PRINTED.

       1400-READ-TRANSACTION.
           READ TRANSACTION-FILE INTO TRANSACTION-RECORD
               AT END
                   SET END-OF-TRANS TO TRUE
               NOT AT END
                   ADD 1 TO WS-TRANS-READ
           END-READ.

      *================================================================*
      * MAIN TRANSACTION PROCESSING LOOP                               *
      *================================================================*
       2000-PROCESS-TRANSACTIONS.
           SET ACCT-NOT-FOUND     TO TRUE
           SET INVALID-TRANS      TO TRUE
           SET NO-PROCESSING-ERROR TO TRUE

           PERFORM 2100-VALIDATE-TRANSACTION
           IF VALID-TRANS
               PERFORM 2200-LOOKUP-ACCOUNT
               IF ACCT-FOUND
                   PERFORM 2300-APPLY-TRANSACTION
               ELSE
                   PERFORM 7100-WRITE-ERROR
                       'ACCOUNT NOT FOUND'
               END-IF
           ELSE
               PERFORM 7100-WRITE-ERROR
                   'INVALID TRANSACTION CODE'
           END-IF

           PERFORM 1400-READ-TRANSACTION.

      *================================================================*
      * TRANSACTION VALIDATION                                         *
      *================================================================*
       2100-VALIDATE-TRANSACTION.
           SET INVALID-TRANS TO TRUE

           IF TR-ACCT-NUMBER = ZEROS
               PERFORM 7100-WRITE-ERROR
                   'ZERO ACCOUNT NUMBER'
               GO TO 2100-EXIT
           END-IF

           IF TR-AMOUNT < ZEROS
               IF NOT TR-ADJUSTMENT
                   PERFORM 7100-WRITE-ERROR
                       'NEGATIVE AMOUNT'
                   GO TO 2100-EXIT
               END-IF
           END-IF

           EVALUATE TRUE
               WHEN TR-DEPOSIT
               WHEN TR-WITHDRAWAL
               WHEN TR-TRANSFER-OUT
               WHEN TR-TRANSFER-IN
               WHEN TR-PAYMENT
               WHEN TR-FEE-CHARGE
               WHEN TR-INTEREST-CREDIT
               WHEN TR-ADJUSTMENT
               WHEN TR-BALANCE-INQUIRY
               WHEN TR-ACCOUNT-CLOSE
                   SET VALID-TRANS TO TRUE
               WHEN OTHER
                   SET INVALID-TRANS TO TRUE
           END-EVALUATE.

       2100-EXIT.
           EXIT.

      *================================================================*
      * ACCOUNT LOOKUP                                                 *
      *================================================================*
       2200-LOOKUP-ACCOUNT.
           MOVE TR-ACCT-NUMBER TO WS-ACCT-NUMBER
           READ MASTER-FILE INTO MASTER-RECORD
               KEY IS WS-ACCT-NUMBER
               INVALID KEY
                   SET ACCT-NOT-FOUND TO TRUE
               NOT INVALID KEY
                   SET ACCT-FOUND TO TRUE
           END-READ.

      *================================================================*
      * APPLY TRANSACTION BASED ON TYPE                                *
      *================================================================*
       2300-APPLY-TRANSACTION.
           IF ACCT-FROZEN
               PERFORM 7100-WRITE-ERROR
                   'ACCOUNT IS FROZEN'
               GO TO 2300-EXIT
           END-IF

           IF ACCT-CLOSED
               IF NOT TR-ADJUSTMENT
                   PERFORM 7100-WRITE-ERROR
                       'ACCOUNT IS CLOSED'
                   GO TO 2300-EXIT
               END-IF
           END-IF

           MOVE WS-BALANCE TO WS-SAVE-BALANCE

           EVALUATE TRUE
               WHEN TR-DEPOSIT
                   PERFORM 3000-PROCESS-DEPOSIT
               WHEN TR-WITHDRAWAL
                   PERFORM 4000-PROCESS-WITHDRAWAL
               WHEN TR-TRANSFER-OUT
                   PERFORM 5000-PROCESS-TRANSFER-OUT
               WHEN TR-TRANSFER-IN
                   PERFORM 5500-PROCESS-TRANSFER-IN
               WHEN TR-PAYMENT
                   PERFORM 4000-PROCESS-WITHDRAWAL
               WHEN TR-FEE-CHARGE
                   PERFORM 6000-PROCESS-FEE
               WHEN TR-INTEREST-CREDIT
                   PERFORM 6500-PROCESS-INTEREST
               WHEN TR-ADJUSTMENT
                   PERFORM 6700-PROCESS-ADJUSTMENT
               WHEN TR-BALANCE-INQUIRY
                   PERFORM 6800-PROCESS-INQUIRY
               WHEN TR-ACCOUNT-CLOSE
                   PERFORM 6900-PROCESS-CLOSE
           END-EVALUATE

           IF NOT PROCESSING-ERROR
               PERFORM 7000-UPDATE-MASTER
               PERFORM 7200-WRITE-AUDIT
               PERFORM 7300-WRITE-REPORT-LINE
               ADD 1 TO WS-TRANS-PROCESSED
           END-IF.

       2300-EXIT.
           EXIT.

      *================================================================*
      * DEPOSIT PROCESSING                                             *
      *================================================================*
       3000-PROCESS-DEPOSIT.
           IF TR-AMOUNT = ZEROS
               PERFORM 7100-WRITE-ERROR
                   'ZERO DEPOSIT AMOUNT'
               SET PROCESSING-ERROR TO TRUE
               GO TO 3000-EXIT
           END-IF

           ADD TR-AMOUNT TO WS-BALANCE
           ADD TR-AMOUNT TO WS-AVAILABLE-BALANCE

           ADD TR-AMOUNT TO WS-TOTAL-DEPOSITS
           ADD TR-AMOUNT TO WS-RECON-TOTAL-CREDITS
           ADD 1 TO WS-DEPOSIT-COUNT

           MOVE WS-CURRENT-DATE TO WS-LAST-ACTIVITY-DATE
           SET NO-PROCESSING-ERROR TO TRUE.

       3000-EXIT.
           EXIT.

      *================================================================*
      * WITHDRAWAL PROCESSING                                         *
      *================================================================*
       4000-PROCESS-WITHDRAWAL.
           IF TR-AMOUNT = ZEROS
               PERFORM 7100-WRITE-ERROR
                   'ZERO WITHDRAWAL AMOUNT'
               SET PROCESSING-ERROR TO TRUE
               GO TO 4000-EXIT
           END-IF

      *    CHECK DAILY WITHDRAWAL LIMITS
           IF SRC-ATM
               IF TR-AMOUNT > WS-DAILY-LIMIT-ATM
                   PERFORM 7100-WRITE-ERROR
                       'ATM DAILY LIMIT EXCEEDED'
                   SET PROCESSING-ERROR TO TRUE
                   GO TO 4000-EXIT
               END-IF
           END-IF

           ADD TR-AMOUNT TO WS-DAILY-WITHDRAWAL-AMT
           IF WS-DAILY-WITHDRAWAL-AMT > WS-MAX-DAILY-WD
               PERFORM 7100-WRITE-ERROR
                   'DAILY WITHDRAWAL LIMIT EXCEEDED'
               SUBTRACT TR-AMOUNT FROM WS-DAILY-WITHDRAWAL-AMT
               SET PROCESSING-ERROR TO TRUE
               GO TO 4000-EXIT
           END-IF

           ADD 1 TO WS-DAILY-WITHDRAWAL-CNT
           IF WS-DAILY-WITHDRAWAL-CNT > WS-MAX-DAILY-WD-COUNT
               PERFORM 7100-WRITE-ERROR
                   'DAILY WITHDRAWAL COUNT EXCEEDED'
               SUBTRACT 1 FROM WS-DAILY-WITHDRAWAL-CNT
               SET PROCESSING-ERROR TO TRUE
               GO TO 4000-EXIT
           END-IF

      *    CHECK SUFFICIENT FUNDS
           COMPUTE WS-WORK-BALANCE =
               WS-AVAILABLE-BALANCE - TR-AMOUNT

           IF WS-WORK-BALANCE < ZEROS
      *        CHECK OVERDRAFT PROTECTION
               IF WS-OVERDRAFT-LIMIT > ZEROS
                   COMPUTE WS-WORK-AMOUNT =
                       WS-AVAILABLE-BALANCE + WS-OVERDRAFT-LIMIT
                   IF TR-AMOUNT > WS-WORK-AMOUNT
                       PERFORM 7100-WRITE-ERROR
                           'INSUFFICIENT FUNDS WITH OVERDRAFT'
                       SET PROCESSING-ERROR TO TRUE
                       GO TO 4000-EXIT
                   ELSE
      *                APPLY OVERDRAFT FEE
                       SUBTRACT WS-OVERDRAFT-FEE
                           FROM WS-BALANCE
                       ADD WS-OVERDRAFT-FEE
                           TO WS-TOTAL-FEES
                   END-IF
               ELSE
                   PERFORM 7100-WRITE-ERROR
                       'INSUFFICIENT FUNDS'
                   SET PROCESSING-ERROR TO TRUE
                   GO TO 4000-EXIT
               END-IF
           END-IF

           SUBTRACT TR-AMOUNT FROM WS-BALANCE
           SUBTRACT TR-AMOUNT FROM WS-AVAILABLE-BALANCE

      *    CHECK MINIMUM BALANCE
           EVALUATE TRUE
               WHEN ACCT-CHECKING
                   IF WS-BALANCE < WS-MIN-BALANCE-CHK
                       PERFORM 6000-ASSESS-LOW-BALANCE-FEE
                   END-IF
               WHEN ACCT-SAVINGS
                   IF WS-BALANCE < WS-MIN-BALANCE-SAV
                       PERFORM 6000-ASSESS-LOW-BALANCE-FEE
                   END-IF
           END-EVALUATE

           ADD TR-AMOUNT TO WS-TOTAL-WITHDRAWALS
           ADD TR-AMOUNT TO WS-RECON-TOTAL-DEBITS
           ADD 1 TO WS-WITHDRAWAL-COUNT

           MOVE WS-CURRENT-DATE TO WS-LAST-ACTIVITY-DATE
           SET NO-PROCESSING-ERROR TO TRUE.

       4000-EXIT.
           EXIT.

      *================================================================*
      * TRANSFER OUT PROCESSING                                        *
      *================================================================*
       5000-PROCESS-TRANSFER-OUT.
           IF TR-AMOUNT = ZEROS
               PERFORM 7100-WRITE-ERROR
                   'ZERO TRANSFER AMOUNT'
               SET PROCESSING-ERROR TO TRUE
               GO TO 5000-EXIT
           END-IF

           IF TR-AMOUNT > WS-MAX-TRANSFER-AMT
               PERFORM 7100-WRITE-ERROR
                   'TRANSFER AMOUNT EXCEEDS LIMIT'
               SET PROCESSING-ERROR TO TRUE
               GO TO 5000-EXIT
           END-IF

           IF TR-TARGET-ACCT = ZEROS
               PERFORM 7100-WRITE-ERROR
                   'NO TARGET ACCOUNT FOR TRANSFER'
               SET PROCESSING-ERROR TO TRUE
               GO TO 5000-EXIT
           END-IF

           IF TR-TARGET-ACCT = TR-ACCT-NUMBER
               PERFORM 7100-WRITE-ERROR
                   'CANNOT TRANSFER TO SAME ACCOUNT'
               SET PROCESSING-ERROR TO TRUE
               GO TO 5000-EXIT
           END-IF

      *    VERIFY SUFFICIENT FUNDS
           IF TR-AMOUNT > WS-AVAILABLE-BALANCE
               PERFORM 7100-WRITE-ERROR
                   'INSUFFICIENT FUNDS FOR TRANSFER'
               SET PROCESSING-ERROR TO TRUE
               GO TO 5000-EXIT
           END-IF

      *    APPLY WIRE FEE IF APPLICABLE
           IF SRC-WIRE
               SUBTRACT WS-WIRE-FEE-DOMESTIC FROM WS-BALANCE
               ADD WS-WIRE-FEE-DOMESTIC TO WS-TOTAL-FEES
           END-IF

           SUBTRACT TR-AMOUNT FROM WS-BALANCE
           SUBTRACT TR-AMOUNT FROM WS-AVAILABLE-BALANCE

           ADD TR-AMOUNT TO WS-TOTAL-TRANSFERS
           ADD TR-AMOUNT TO WS-RECON-TOTAL-DEBITS
           ADD 1 TO WS-TRANSFER-COUNT

           MOVE WS-CURRENT-DATE TO WS-LAST-ACTIVITY-DATE
           SET NO-PROCESSING-ERROR TO TRUE.

       5000-EXIT.
           EXIT.

      *================================================================*
      * TRANSFER IN PROCESSING                                         *
      *================================================================*
       5500-PROCESS-TRANSFER-IN.
           ADD TR-AMOUNT TO WS-BALANCE
           ADD TR-AMOUNT TO WS-AVAILABLE-BALANCE

           ADD TR-AMOUNT TO WS-RECON-TOTAL-CREDITS
           ADD 1 TO WS-TRANSFER-COUNT

           MOVE WS-CURRENT-DATE TO WS-LAST-ACTIVITY-DATE
           SET NO-PROCESSING-ERROR TO TRUE.

      *================================================================*
      * FEE PROCESSING                                                 *
      *================================================================*
       6000-PROCESS-FEE.
           IF TR-AMOUNT = ZEROS
               MOVE WS-MONTHLY-FEE TO TR-AMOUNT
           END-IF

           SUBTRACT TR-AMOUNT FROM WS-BALANCE
           ADD TR-AMOUNT TO WS-TOTAL-FEES
           ADD TR-AMOUNT TO WS-RECON-TOTAL-DEBITS

           MOVE WS-CURRENT-DATE TO WS-LAST-ACTIVITY-DATE
           SET NO-PROCESSING-ERROR TO TRUE.

       6000-ASSESS-LOW-BALANCE-FEE.
           MOVE 15.00 TO WS-FEE-AMOUNT
           SUBTRACT WS-FEE-AMOUNT FROM WS-BALANCE
           ADD WS-FEE-AMOUNT TO WS-TOTAL-FEES
           ADD WS-FEE-AMOUNT TO WS-RECON-TOTAL-DEBITS.

      *================================================================*
      * INTEREST CREDIT PROCESSING                                     *
      *================================================================*
       6500-PROCESS-INTEREST.
           IF TR-AMOUNT > ZEROS
      *        USE SPECIFIED AMOUNT
               ADD TR-AMOUNT TO WS-BALANCE
               ADD TR-AMOUNT TO WS-INTEREST-ACCRUED
           ELSE
      *        CALCULATE INTEREST
               MOVE WS-INTEREST-RATE TO WS-INT-ANNUAL-RATE
               DIVIDE WS-INT-ANNUAL-RATE BY 365
                   GIVING WS-INT-DAILY-RATE ROUNDED
               MOVE 30 TO WS-INT-DAYS
               MOVE WS-BALANCE TO WS-INT-PRINCIPAL
               COMPUTE WS-INT-EARNED ROUNDED =
                   WS-INT-PRINCIPAL * WS-INT-DAILY-RATE
                   * WS-INT-DAYS
               ADD WS-INT-EARNED TO WS-BALANCE
               ADD WS-INT-EARNED TO WS-INTEREST-ACCRUED
               MOVE WS-INT-EARNED TO TR-AMOUNT
           END-IF

           ADD TR-AMOUNT TO WS-TOTAL-INTEREST
           ADD TR-AMOUNT TO WS-RECON-TOTAL-CREDITS

           MOVE WS-CURRENT-DATE TO WS-LAST-ACTIVITY-DATE
           SET NO-PROCESSING-ERROR TO TRUE.

      *================================================================*
      * ADJUSTMENT PROCESSING                                          *
      *================================================================*
       6700-PROCESS-ADJUSTMENT.
           ADD TR-AMOUNT TO WS-BALANCE
           ADD TR-AMOUNT TO WS-AVAILABLE-BALANCE

           IF TR-AMOUNT > ZEROS
               ADD TR-AMOUNT TO WS-RECON-TOTAL-CREDITS
           ELSE
               COMPUTE WS-WORK-AMOUNT = TR-AMOUNT * -1
               ADD WS-WORK-AMOUNT TO WS-RECON-TOTAL-DEBITS
           END-IF

           MOVE WS-CURRENT-DATE TO WS-LAST-ACTIVITY-DATE
           SET NO-PROCESSING-ERROR TO TRUE.

      *================================================================*
      * BALANCE INQUIRY PROCESSING                                     *
      *================================================================*
       6800-PROCESS-INQUIRY.
           ADD 1 TO WS-INQUIRY-COUNT
           MOVE WS-CURRENT-DATE TO WS-LAST-ACTIVITY-DATE
           SET NO-PROCESSING-ERROR TO TRUE.

      *================================================================*
      * ACCOUNT CLOSE PROCESSING                                       *
      *================================================================*
       6900-PROCESS-CLOSE.
           IF WS-BALANCE NOT = ZEROS
               PERFORM 7100-WRITE-ERROR
                   'CANNOT CLOSE - NON-ZERO BALANCE'
               SET PROCESSING-ERROR TO TRUE
               GO TO 6900-EXIT
           END-IF

           IF WS-HOLD-AMOUNT > ZEROS
               PERFORM 7100-WRITE-ERROR
                   'CANNOT CLOSE - HOLDS EXIST'
               SET PROCESSING-ERROR TO TRUE
               GO TO 6900-EXIT
           END-IF

           SET ACCT-CLOSED TO TRUE
           MOVE WS-CURRENT-DATE TO WS-LAST-ACTIVITY-DATE
           SET NO-PROCESSING-ERROR TO TRUE.

       6900-EXIT.
           EXIT.

      *================================================================*
      * FILE UPDATE AND OUTPUT ROUTINES                                *
      *================================================================*
       7000-UPDATE-MASTER.
           REWRITE MASTER-RECORD
           IF NOT MASTER-OK
               DISPLAY 'ERROR REWRITING MASTER: '
                       WS-ACCT-NUMBER ' STATUS: ' WS-MASTER-STATUS
               ADD 1 TO WS-ERROR-COUNT
           END-IF.

       7100-WRITE-ERROR.
           ADD 1 TO WS-TRANS-REJECTED
           ADD 1 TO WS-ERROR-COUNT

           MOVE WS-TIMESTAMP TO ER-TIMESTAMP
           MOVE TR-ACCT-NUMBER TO ER-ACCT-NUMBER
           MOVE TR-TRANS-CODE TO ER-TRANS-CODE
           MOVE 'E001' TO ER-ERROR-CODE
           MOVE SPACES TO ER-ERROR-MESSAGE
           WRITE ERROR-RECORD
           IF NOT ERROR-OK
               DISPLAY 'ERROR WRITING ERROR FILE: '
                       WS-ERROR-STATUS
           END-IF.

       7200-WRITE-AUDIT.
           MOVE WS-TIMESTAMP TO AU-TIMESTAMP
           MOVE TR-ACCT-NUMBER TO AU-ACCT-NUMBER
           MOVE TR-TRANS-CODE TO AU-TRANS-CODE
           MOVE TR-AMOUNT TO AU-AMOUNT
           MOVE WS-SAVE-BALANCE TO AU-BALANCE-BEFORE
           MOVE WS-BALANCE TO AU-BALANCE-AFTER
           SET AU-SUCCESS TO TRUE
           MOVE TR-TELLER-ID TO AU-TELLER-ID
           MOVE TR-BRANCH-CODE TO AU-BRANCH-CODE
           MOVE TR-REFERENCE-NUM TO AU-REFERENCE
           MOVE TR-DESCRIPTION TO AU-DESCRIPTION
           WRITE AUDIT-RECORD
           IF NOT AUDIT-OK
               DISPLAY 'ERROR WRITING AUDIT FILE: '
                       WS-AUDIT-STATUS
           END-IF.

       7300-WRITE-REPORT-LINE.
           IF WS-LINES-PRINTED > 55
               PERFORM 1300-PRINT-HEADERS
           END-IF

           MOVE TR-ACCT-NUMBER TO WS-RPT-ACCT
           MOVE TR-TRANS-CODE TO WS-RPT-TYPE
           MOVE TR-AMOUNT TO WS-RPT-AMOUNT
           MOVE WS-BALANCE TO WS-RPT-BALANCE
           MOVE 'OK' TO WS-RPT-STATUS
           MOVE TR-REFERENCE-NUM TO WS-RPT-REF
           WRITE REPORT-RECORD FROM WS-RPT-DETAIL
               AFTER ADVANCING 1 LINE
           ADD 1 TO WS-LINES-PRINTED.

      *================================================================*
      * DAILY RECONCILIATION                                           *
      *================================================================*
       8000-RECONCILIATION.
           COMPUTE WS-NET-ACTIVITY =
               WS-TOTAL-DEPOSITS
               + WS-TOTAL-INTEREST
               - WS-TOTAL-WITHDRAWALS
               - WS-TOTAL-FEES

           COMPUTE WS-RECON-DIFFERENCE =
               WS-RECON-TOTAL-CREDITS - WS-RECON-TOTAL-DEBITS

           IF WS-RECON-DIFFERENCE = WS-NET-ACTIVITY
               SET RECON-BALANCED TO TRUE
               MOVE 'BALANCED' TO WS-RECON-STATUS
           ELSE
               SET RECON-OUT-OF-BAL TO TRUE
               MOVE 'OUT OF BAL' TO WS-RECON-STATUS
               DISPLAY '*** RECONCILIATION OUT OF BALANCE ***'
               DISPLAY 'NET ACTIVITY: ' WS-NET-ACTIVITY
               DISPLAY 'RECON DIFF:   ' WS-RECON-DIFFERENCE
           END-IF

           PERFORM 8100-WRITE-RECON-REPORT.

       8100-WRITE-RECON-REPORT.
           MOVE SPACES TO RECON-RECORD
           STRING 'RECONCILIATION STATUS: '
                  DELIMITED BY SIZE
                  WS-RECON-STATUS
                  DELIMITED BY SIZE
               INTO RECON-RECORD
           END-STRING
           WRITE RECON-RECORD

           MOVE SPACES TO RECON-RECORD
           MOVE WS-RECON-TOTAL-CREDITS TO WS-DISPLAY-AMOUNT
           STRING 'TOTAL CREDITS:  '
                  DELIMITED BY SIZE
                  WS-DISPLAY-AMOUNT
                  DELIMITED BY SIZE
               INTO RECON-RECORD
           END-STRING
           WRITE RECON-RECORD

           MOVE SPACES TO RECON-RECORD
           MOVE WS-RECON-TOTAL-DEBITS TO WS-DISPLAY-AMOUNT
           STRING 'TOTAL DEBITS:   '
                  DELIMITED BY SIZE
                  WS-DISPLAY-AMOUNT
                  DELIMITED BY SIZE
               INTO RECON-RECORD
           END-STRING
           WRITE RECON-RECORD

           MOVE SPACES TO RECON-RECORD
           MOVE WS-NET-ACTIVITY TO WS-DISPLAY-AMOUNT
           STRING 'NET ACTIVITY:   '
                  DELIMITED BY SIZE
                  WS-DISPLAY-AMOUNT
                  DELIMITED BY SIZE
               INTO RECON-RECORD
           END-STRING
           WRITE RECON-RECORD.

      *================================================================*
      * FINALIZATION AND SUMMARY                                       *
      *================================================================*
       9000-FINALIZE.
           PERFORM 9100-PRINT-SUMMARY
           PERFORM 9200-CLOSE-FILES
           PERFORM 9300-DISPLAY-TOTALS.

       9100-PRINT-SUMMARY.
           IF WS-LINES-PRINTED > 45
               PERFORM 1300-PRINT-HEADERS
           END-IF

           MOVE SPACES TO REPORT-RECORD
           WRITE REPORT-RECORD
               AFTER ADVANCING 2 LINES

           MOVE WS-TRANS-READ TO WS-RPT-SUM-READ
           WRITE REPORT-RECORD FROM WS-RPT-SUM-1
               AFTER ADVANCING 1 LINE

           MOVE WS-TRANS-PROCESSED TO WS-RPT-SUM-PROC
           WRITE REPORT-RECORD FROM WS-RPT-SUM-2
               AFTER ADVANCING 1 LINE

           MOVE WS-TRANS-REJECTED TO WS-RPT-SUM-REJ
           WRITE REPORT-RECORD FROM WS-RPT-SUM-3
               AFTER ADVANCING 1 LINE

           MOVE SPACES TO REPORT-RECORD
           WRITE REPORT-RECORD AFTER ADVANCING 1 LINE

           MOVE WS-TOTAL-DEPOSITS TO WS-RPT-SUM-DEP
           WRITE REPORT-RECORD FROM WS-RPT-SUM-4
               AFTER ADVANCING 1 LINE

           MOVE WS-TOTAL-WITHDRAWALS TO WS-RPT-SUM-WD
           WRITE REPORT-RECORD FROM WS-RPT-SUM-5
               AFTER ADVANCING 1 LINE

           MOVE WS-TOTAL-TRANSFERS TO WS-RPT-SUM-XFR
           WRITE REPORT-RECORD FROM WS-RPT-SUM-6
               AFTER ADVANCING 1 LINE

           MOVE WS-NET-ACTIVITY TO WS-RPT-SUM-NET
           WRITE REPORT-RECORD FROM WS-RPT-SUM-7
               AFTER ADVANCING 1 LINE

           WRITE REPORT-RECORD FROM WS-RPT-FOOTER
               AFTER ADVANCING 3 LINES.

       9200-CLOSE-FILES.
           CLOSE MASTER-FILE
           CLOSE TRANSACTION-FILE
           CLOSE REPORT-FILE
           CLOSE AUDIT-FILE
           CLOSE ERROR-FILE
           CLOSE RECONCILIATION-FILE.

       9300-DISPLAY-TOTALS.
           DISPLAY SPACES
           DISPLAY '=========================================='
           DISPLAY ' DAILY PROCESSING SUMMARY'
           DISPLAY '=========================================='
           DISPLAY ' DATE:              ' WS-FORMATTED-DATE
           DISPLAY ' TIME:              ' WS-FORMATTED-TIME
           DISPLAY '------------------------------------------'
           MOVE WS-TRANS-READ TO WS-DISPLAY-AMOUNT
           DISPLAY ' TRANS READ:        ' WS-DISPLAY-AMOUNT
           MOVE WS-TRANS-PROCESSED TO WS-DISPLAY-AMOUNT
           DISPLAY ' TRANS PROCESSED:   ' WS-DISPLAY-AMOUNT
           MOVE WS-TRANS-REJECTED TO WS-DISPLAY-AMOUNT
           DISPLAY ' TRANS REJECTED:    ' WS-DISPLAY-AMOUNT
           DISPLAY '------------------------------------------'
           MOVE WS-TOTAL-DEPOSITS TO WS-DISPLAY-AMOUNT
           DISPLAY ' TOTAL DEPOSITS:    ' WS-DISPLAY-AMOUNT
           MOVE WS-TOTAL-WITHDRAWALS TO WS-DISPLAY-AMOUNT
           DISPLAY ' TOTAL WITHDRAWALS: ' WS-DISPLAY-AMOUNT
           MOVE WS-TOTAL-TRANSFERS TO WS-DISPLAY-AMOUNT
           DISPLAY ' TOTAL TRANSFERS:   ' WS-DISPLAY-AMOUNT
           MOVE WS-TOTAL-FEES TO WS-DISPLAY-AMOUNT
           DISPLAY ' TOTAL FEES:        ' WS-DISPLAY-AMOUNT
           MOVE WS-TOTAL-INTEREST TO WS-DISPLAY-AMOUNT
           DISPLAY ' TOTAL INTEREST:    ' WS-DISPLAY-AMOUNT
           DISPLAY '------------------------------------------'
           MOVE WS-NET-ACTIVITY TO WS-DISPLAY-AMOUNT
           DISPLAY ' NET ACTIVITY:      ' WS-DISPLAY-AMOUNT
           DISPLAY '------------------------------------------'
           DISPLAY ' RECON STATUS:      ' WS-RECON-STATUS
           DISPLAY ' ERRORS:            ' WS-ERROR-COUNT
           DISPLAY '=========================================='.

      *================================================================*
      * ABEND ROUTINE                                                  *
      *================================================================*
       9999-ABEND-ROUTINE.
           DISPLAY '*** ABEND — CRITICAL ERROR ***'
           DISPLAY 'MASTER STATUS: ' WS-MASTER-STATUS
           DISPLAY 'TRANS STATUS:  ' WS-TRANS-STATUS
           DISPLAY 'REPORT STATUS: ' WS-REPORT-STATUS
           DISPLAY 'AUDIT STATUS:  ' WS-AUDIT-STATUS
           DISPLAY 'ERROR STATUS:  ' WS-ERROR-STATUS
           DISPLAY 'RECON STATUS:  ' WS-RECON-STATUS
           STOP RUN.
