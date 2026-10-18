# Six-year backfill numbers (2017--2022)

## Table 5.1 inputs (populations, q0=0.10)
- 2017: PRE N=1310 K=131 | TURN N=3899 K=390 | full-eligible=5209 | paired cohort=521 | E3 pairs=4168
- 2018: PRE N=1345 K=135 | TURN N=3873 K=388 | full-eligible=5218 | paired cohort=523 | E3 pairs=4184
- 2019: PRE N=1252 K=126 | TURN N=3888 K=389 | full-eligible=5140 | paired cohort=515 | E3 pairs=4120
- 2020: PRE N=675 K=68 | TURN N=4053 K=406 | full-eligible=4728 | paired cohort=474 | E3 pairs=3792
- 2021: PRE N=1297 K=130 | TURN N=3930 K=393 | full-eligible=5227 | paired cohort=523 | E3 pairs=4184
- 2022: PRE N=1422 K=143 | TURN N=3884 K=389 | full-eligible=5306 | paired cohort=532 | E3 pairs=4256

## E1 screening loss at q0=0.10 (L^att, 95% CI for DELAY)
- 2017 PRE: Delay=0.1054 (repl 49/131); Delay+Passenger=0.0626 (repl 40/131); Delay+Downstream=0.1054 (repl 49/131)
- 2017 TURN: Delay=0.1159 (repl 166/390); Delay+Passenger=0.0715 (repl 126/390); Delay+Downstream=0.1159 (repl 166/390)
- 2018 PRE: Delay=0.1607 (repl 62/135); Delay+Passenger=0.0877 (repl 45/135); Delay+Downstream=0.1603 (repl 62/135)
- 2018 TURN: Delay=0.1476 (repl 173/388); Delay+Passenger=0.1053 (repl 138/388); Delay+Downstream=0.1468 (repl 173/388)
- 2019 PRE: Delay=0.1336 (repl 51/126); Delay+Passenger=0.0842 (repl 44/126); Delay+Downstream=0.1336 (repl 51/126)
- 2019 TURN: Delay=0.1233 (repl 154/389); Delay+Passenger=0.0836 (repl 127/389); Delay+Downstream=0.1234 (repl 154/389)
- 2020 PRE: Delay=0.1006 (repl 27/68); Delay+Passenger=0.0700 (repl 21/68); Delay+Downstream=0.0988 (repl 27/68)
- 2020 TURN: Delay=0.1068 (repl 170/406); Delay+Passenger=0.0674 (repl 130/406); Delay+Downstream=0.1058 (repl 170/406)
- 2021 PRE: Delay=0.1538 (repl 67/130); Delay+Passenger=0.1143 (repl 62/130); Delay+Downstream=0.1538 (repl 67/130)
- 2021 TURN: Delay=0.1562 (repl 207/393); Delay+Passenger=0.1127 (repl 168/393); Delay+Downstream=0.1553 (repl 206/393)
- 2022 PRE: Delay=0.1840 (repl 76/143); Delay+Passenger=0.1721 (repl 65/143); Delay+Downstream=0.1813 (repl 75/143)
- 2022 TURN: Delay=0.1811 (repl 215/389); Delay+Passenger=0.1446 (repl 171/389); Delay+Downstream=0.1809 (repl 215/389)

## E1 q grid (L^att by q)
- Delay PRE: q=0.05: mean=0.1742 [0.1366,0.2008]; q=0.1: mean=0.1397 [0.1006,0.1840]; q=0.2: mean=0.0949 [0.0760,0.1223]; q=0.3: mean=0.0713 [0.0508,0.0876]
- Delay TURN: q=0.05: mean=0.1651 [0.1342,0.1958]; q=0.1: mean=0.1385 [0.1068,0.1811]; q=0.2: mean=0.0951 [0.0756,0.1185]; q=0.3: mean=0.0688 [0.0511,0.0863]
- Delay+Passenger PRE: q=0.05: mean=0.1180 [0.0703,0.1798]; q=0.1: mean=0.0985 [0.0626,0.1721]; q=0.2: mean=0.0854 [0.0569,0.1161]; q=0.3: mean=0.0764 [0.0622,0.0983]
- Delay+Passenger TURN: q=0.05: mean=0.1125 [0.0681,0.1688]; q=0.1: mean=0.0975 [0.0674,0.1446]; q=0.2: mean=0.0823 [0.0644,0.1084]; q=0.3: mean=0.0724 [0.0572,0.0879]
- Delay+Downstream PRE: q=0.05: mean=0.1739 [0.1366,0.2008]; q=0.1: mean=0.1389 [0.0988,0.1813]; q=0.2: mean=0.0951 [0.0760,0.1225]; q=0.3: mean=0.0713 [0.0520,0.0883]
- Delay+Downstream TURN: q=0.05: mean=0.1649 [0.1331,0.1962]; q=0.1: mean=0.1380 [0.1058,0.1809]; q=0.2: mean=0.0946 [0.0751,0.1187]; q=0.3: mean=0.0684 [0.0508,0.0876]

## E2 paired contrasts
- 2017 cohort=521:
    - ROLLING_HISTORY (CURRENT_JOINT): displaced_share=0.236084 L_att=0.032031 [0.025463,0.039228] A0=0.341651 A5=0.591171 L_rec=0.667648 [0.602759,0.738231] dJ=26.95556 Vref=40.37393
    - DISTRIBUTIONAL_INFORMATION (HISTORY_POINT): displaced_share=0.857965 L_att=0.498604 [0.470785,0.524057] A0=0.226488 A5=0.560461 L_rec=0.914488 [0.878036,0.944696] dJ=36.921479 Vref=40.37393
    - CROSS_STATE_DEPENDENCE (HISTORY_MARGINAL_EXACT): displaced_share=0.019194 L_att=0.000977 [0.000405,0.001826] A0=0.692898 A5=0.896353 L_rec=0.109535 [0.081799,0.141628] dJ=4.422366 Vref=40.37393
    - MARGINAL_UNCERTAINTY (POINT_MINUS_MARGINAL): displaced_share=None L_att=0.496479 [0.495885,0.497084] A0=None A5=None L_rec=0.804005 [0.803004,0.805044] dJ=32.499113 Vref=None
- 2018 cohort=523:
    - ROLLING_HISTORY (CURRENT_JOINT): displaced_share=0.16826 L_att=0.023294 [0.018008,0.029243] A0=0.239006 A5=0.456979 L_rec=0.619382 [0.562184,0.683304] dJ=52.730396 Vref=85.133935
    - DISTRIBUTIONAL_INFORMATION (HISTORY_POINT): displaced_share=0.875717 L_att=0.505027 [0.478286,0.530935] A0=0.130019 A5=0.307839 L_rec=0.981401 [0.971781,0.989225] dJ=83.550491 Vref=85.133935
    - CROSS_STATE_DEPENDENCE (HISTORY_MARGINAL_EXACT): displaced_share=0.01912 L_att=0.001132 [0.000109,0.002019] A0=0.585086 A5=0.921606 L_rec=0.09353 [0.071811,0.117769] dJ=7.96255 Vref=85.133935
    - MARGINAL_UNCERTAINTY (POINT_MINUS_MARGINAL): displaced_share=None L_att=0.503853 [0.503284,0.504448] A0=None A5=None L_rec=0.887864 [0.887308,0.888421] dJ=75.587941 Vref=None
- 2019 cohort=515:
    - ROLLING_HISTORY (CURRENT_JOINT): displaced_share=0.180583 L_att=0.025349 [0.021399,0.032987] A0=0.353398 A5=0.666019 L_rec=0.695723 [0.635917,0.761208] dJ=29.316249 Vref=42.137794
    - DISTRIBUTIONAL_INFORMATION (HISTORY_POINT): displaced_share=0.885437 L_att=0.529148 [0.505164,0.554328] A0=0.240777 A5=0.654369 L_rec=0.932148 [0.89754,0.961598] dJ=39.278665 Vref=42.137794
    - CROSS_STATE_DEPENDENCE (HISTORY_MARGINAL_EXACT): displaced_share=0.019417 L_att=0.000871 [0.000356,0.001512] A0=0.730097 A5=0.959223 L_rec=0.085317 [0.062349,0.112857] dJ=3.595075 Vref=42.137794
    - MARGINAL_UNCERTAINTY (POINT_MINUS_MARGINAL): displaced_share=None L_att=0.52911 [0.528588,0.529672] A0=None A5=None L_rec=0.846573 [0.845653,0.847501] dJ=35.68359 Vref=None
- 2020 cohort=474:
    - ROLLING_HISTORY (CURRENT_JOINT): displaced_share=0.898734 L_att=0.506049 [0.481988,0.528506] A0=0.086498 A5=0.424051 L_rec=0.997736 [0.994365,1.000621] dJ=41.262117 Vref=41.355734
    - DISTRIBUTIONAL_INFORMATION (HISTORY_POINT): displaced_share=0.841772 L_att=0.431314 [0.407139,0.45628] A0=0.170886 A5=0.421941 L_rec=0.896278 [0.872065,0.919165] dJ=37.066227 Vref=41.355734
    - CROSS_STATE_DEPENDENCE (HISTORY_MARGINAL_EXACT): displaced_share=0.012658 L_att=0.00065 [4e-05,0.001248] A0=0.630802 A5=0.932489 L_rec=0.090585 [0.072713,0.113096] dJ=3.746199 Vref=41.355734
    - MARGINAL_UNCERTAINTY (POINT_MINUS_MARGINAL): displaced_share=None L_att=0.431385 [0.430788,0.431969] A0=None A5=None L_rec=0.805772 [0.805113,0.806412] dJ=33.320028 Vref=None
- 2021 cohort=523:
    - ROLLING_HISTORY (CURRENT_JOINT): displaced_share=0.122371 L_att=0.010113 [0.007454,0.013386] A0=0.49522 A5=0.6826 L_rec=0.310202 [0.261597,0.36622] dJ=20.289953 Vref=65.408759
    - DISTRIBUTIONAL_INFORMATION (HISTORY_POINT): displaced_share=0.85086 L_att=0.413432 [0.386456,0.436656] A0=0.152964 A5=0.359465 L_rec=0.953465 [0.936543,0.968023] dJ=62.364933 Vref=65.408759
    - CROSS_STATE_DEPENDENCE (HISTORY_MARGINAL_EXACT): displaced_share=0.024857 L_att=0.002614 [0.000944,0.004881] A0=0.617591 A5=0.898662 L_rec=0.105057 [0.080936,0.132861] dJ=6.871641 Vref=65.408759
    - MARGINAL_UNCERTAINTY (POINT_MINUS_MARGINAL): displaced_share=None L_att=0.409511 [0.408956,0.410068] A0=None A5=None L_rec=0.84818 [0.84744,0.848909] dJ=55.493292 Vref=None
- 2022 cohort=532:
    - ROLLING_HISTORY (CURRENT_JOINT): displaced_share=0.178571 L_att=0.024353 [0.018008,0.02987] A0=0.298872 A5=0.488722 L_rec=0.59472 [0.53765,0.657639] dJ=46.579393 Vref=78.321511
    - DISTRIBUTIONAL_INFORMATION (HISTORY_POINT): displaced_share=0.887218 L_att=0.49945 [0.476756,0.524648] A0=0.129699 A5=0.328947 L_rec=0.957455 [0.93881,0.974076] dJ=74.989315 Vref=78.321511
    - CROSS_STATE_DEPENDENCE (HISTORY_MARGINAL_EXACT): displaced_share=0.037594 L_att=0.00262 [0.001254,0.004813] A0=0.580827 A5=0.87594 L_rec=0.124659 [0.096584,0.156966] dJ=9.763483 Vref=78.321511
    - MARGINAL_UNCERTAINTY (POINT_MINUS_MARGINAL): displaced_share=None L_att=0.497873 [0.497331,0.498445] A0=None A5=None L_rec=0.832998 [0.832199,0.833785] dJ=65.225831 Vref=None

## E3 objective rows
- 2017 Balanced: agreement=0.692898 dep-sensitive=0.307102 mean|du|=3.003839 activation=0.84261 zeroV=0.15739 medianV=0.017979 medianMargin=0.013596
- 2017 Flight: agreement=0.738964 dep-sensitive=0.261036 mean|du|=2.31286 activation=0.838772 zeroV=0.161228 medianV=0.021858 medianMargin=0.013114
- 2017 Passenger: agreement=0.635317 dep-sensitive=0.364683 mean|du|=3.474088 activation=0.880998 zeroV=0.119002 medianV=0.031015 medianMargin=0.014843
- 2017 Resource: agreement=0.771593 dep-sensitive=0.228407 mean|du|=1.986564 activation=0.631478 zeroV=0.368522 medianV=0.003904 medianMargin=0.009801
- 2018 Balanced: agreement=0.585086 dep-sensitive=0.414914 mean|du|=3.250478 activation=0.90631 zeroV=0.09369 medianV=0.136122 medianMargin=0.019952
- 2018 Flight: agreement=0.592734 dep-sensitive=0.407266 mean|du|=3.221797 activation=0.908222 zeroV=0.091778 medianV=0.096003 medianMargin=0.01805
- 2018 Passenger: agreement=0.564054 dep-sensitive=0.435946 mean|du|=3.021033 activation=0.936902 zeroV=0.063098 medianV=0.255822 medianMargin=0.019791
- 2018 Resource: agreement=0.608031 dep-sensitive=0.391969 mean|du|=2.638623 activation=0.795411 zeroV=0.204589 medianV=0.075058 medianMargin=0.021428
- 2019 Balanced: agreement=0.730097 dep-sensitive=0.269903 mean|du|=1.883495 activation=0.823301 zeroV=0.176699 medianV=0.023103 medianMargin=0.014063
- 2019 Flight: agreement=0.735922 dep-sensitive=0.264078 mean|du|=1.84466 activation=0.848544 zeroV=0.151456 medianV=0.027725 medianMargin=0.013327
- 2019 Passenger: agreement=0.664078 dep-sensitive=0.335922 mean|du|=2.475728 activation=0.842718 zeroV=0.157282 medianV=0.0399 medianMargin=0.01462
- 2019 Resource: agreement=0.753398 dep-sensitive=0.246602 mean|du|=1.902913 activation=0.671845 zeroV=0.328155 medianV=0.006938 medianMargin=0.014845
- 2020 Balanced: agreement=0.630802 dep-sensitive=0.369198 mean|du|=3.343882 activation=0.915612 zeroV=0.084388 medianV=0.054992 medianMargin=0.016284
- 2020 Flight: agreement=0.660338 dep-sensitive=0.339662 mean|du|=3.375527 activation=0.902954 zeroV=0.097046 medianV=0.048923 medianMargin=0.014226
- 2020 Passenger: agreement=0.563291 dep-sensitive=0.436709 mean|du|=2.921941 activation=0.92827 zeroV=0.07173 medianV=0.120626 medianMargin=0.016864
- 2020 Resource: agreement=0.723629 dep-sensitive=0.276371 mean|du|=3.523207 activation=0.835443 zeroV=0.164557 medianV=0.014812 medianMargin=0.014621
- 2021 Balanced: agreement=0.617591 dep-sensitive=0.382409 mean|du|=3.556405 activation=0.885277 zeroV=0.114723 medianV=0.110893 medianMargin=0.018181
- 2021 Flight: agreement=0.650096 dep-sensitive=0.349904 mean|du|=3.32696 activation=0.883365 zeroV=0.116635 medianV=0.084945 medianMargin=0.016654
- 2021 Passenger: agreement=0.546845 dep-sensitive=0.453155 mean|du|=4.302103 activation=0.92543 zeroV=0.07457 medianV=0.206355 medianMargin=0.018856
- 2021 Resource: agreement=0.705545 dep-sensitive=0.294455 mean|du|=2.982792 activation=0.833652 zeroV=0.166348 medianV=0.051631 medianMargin=0.019786
- 2022 Balanced: agreement=0.580827 dep-sensitive=0.419173 mean|du|=4.699248 activation=0.902256 zeroV=0.097744 medianV=0.123689 medianMargin=0.017923
- 2022 Flight: agreement=0.612782 dep-sensitive=0.387218 mean|du|=4.379699 activation=0.885338 zeroV=0.114662 medianV=0.087472 medianMargin=0.015942
- 2022 Passenger: agreement=0.56391 dep-sensitive=0.43609 mean|du|=4.172932 activation=0.913534 zeroV=0.086466 medianV=0.234675 medianMargin=0.018081
- 2022 Resource: agreement=0.612782 dep-sensitive=0.387218 mean|du|=4.370301 activation=0.785714 zeroV=0.214286 medianV=0.054525 medianMargin=0.018981

## E4 cohort-size ladder (M5-b battery, reproduced in the cloud run)
- 2017: decision=N_GRID_UPPER_BOUND_REACHED evaluation_E=4096 failed_instances=11 (eval=11, fit=0)
- 2018: decision=N_GRID_UPPER_BOUND_REACHED evaluation_E=4096 failed_instances=11 (eval=11, fit=0)
- 2019: decision=N_GRID_UPPER_BOUND_REACHED evaluation_E=4096 failed_instances=11 (eval=11, fit=0)
- 2020: decision=N_GRID_UPPER_BOUND_REACHED evaluation_E=4096 failed_instances=20 (eval=11, fit=9)
- 2021: decision=N_GRID_UPPER_BOUND_REACHED evaluation_E=4096 failed_instances=12 (eval=12, fit=0)
- 2022: decision=N_GRID_UPPER_BOUND_REACHED evaluation_E=4096 failed_instances=11 (eval=11, fit=0)
