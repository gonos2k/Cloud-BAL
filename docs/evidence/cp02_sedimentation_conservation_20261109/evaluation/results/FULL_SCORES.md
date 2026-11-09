# Controlled sedimentation forecast scoring

Candidate satisfies 19/26 fixed conditions. Current B1 remains the adopted baseline pending a separate decision.
Each value is scored independently at its lead and threshold over the same 3,688 RN1 points; there is no averaging across leads or thresholds.
Recount using `python docs/evidence/cp02_sedimentation_conservation_20261109/evaluation/evaluate.py --recount PATH_TO_THIS_RESULT --output NEW_SCRATCH_DIRECTORY`. This requires the SHA-pinned repository scorers, NumPy, Matplotlib, netCDF4 and pinned font; it does not read forecast histories.
Weak-observed transitions use 0.1 ≤ observed < 1 mm and forecast threshold 0.1 mm; dry-observed transitions use observed < 0.1 mm. Strong transitions use the 5 mm threshold and split observed ≥ 5 versus < 5 mm.

## Categorical scores

| Lead | Threshold mm | Case | Hit | Miss | False alarm | CSI |
|---:|---:|---|---:|---:|---:|---:|
| 1 | 0.1 | ORIGINAL | 642 | 951 | 54 | 0.389800 |
| 1 | 0.5 | ORIGINAL | 382 | 754 | 85 | 0.312858 |
| 1 | 1 | ORIGINAL | 265 | 448 | 109 | 0.322384 |
| 1 | 2.5 | ORIGINAL | 163 | 188 | 105 | 0.357456 |
| 1 | 5 | ORIGINAL | 74 | 80 | 115 | 0.275093 |
| 1 | 10 | ORIGINAL | 7 | 52 | 83 | 0.049296 |
| 1 | 0.1 | IMPROVED_BG_FIXED | 721 | 872 | 86 | 0.429422 |
| 1 | 0.5 | IMPROVED_BG_FIXED | 403 | 733 | 91 | 0.328443 |
| 1 | 1 | IMPROVED_BG_FIXED | 271 | 442 | 111 | 0.328883 |
| 1 | 2.5 | IMPROVED_BG_FIXED | 167 | 184 | 104 | 0.367033 |
| 1 | 5 | IMPROVED_BG_FIXED | 76 | 78 | 114 | 0.283582 |
| 1 | 10 | IMPROVED_BG_FIXED | 10 | 49 | 83 | 0.070423 |
| 1 | 0.1 | CONSERVATIVE_SEDIMENTATION | 759 | 834 | 102 | 0.447788 |
| 1 | 0.5 | CONSERVATIVE_SEDIMENTATION | 420 | 716 | 97 | 0.340633 |
| 1 | 1 | CONSERVATIVE_SEDIMENTATION | 278 | 435 | 125 | 0.331742 |
| 1 | 2.5 | CONSERVATIVE_SEDIMENTATION | 177 | 174 | 109 | 0.384783 |
| 1 | 5 | CONSERVATIVE_SEDIMENTATION | 90 | 64 | 122 | 0.326087 |
| 1 | 10 | CONSERVATIVE_SEDIMENTATION | 11 | 48 | 87 | 0.075342 |
| 2 | 0.1 | ORIGINAL | 708 | 959 | 427 | 0.338109 |
| 2 | 0.5 | ORIGINAL | 397 | 716 | 212 | 0.299623 |
| 2 | 1 | ORIGINAL | 249 | 444 | 156 | 0.293286 |
| 2 | 2.5 | ORIGINAL | 116 | 267 | 106 | 0.237219 |
| 2 | 5 | ORIGINAL | 59 | 159 | 107 | 0.181538 |
| 2 | 10 | ORIGINAL | 23 | 56 | 87 | 0.138554 |
| 2 | 0.1 | IMPROVED_BG_FIXED | 686 | 981 | 456 | 0.323128 |
| 2 | 0.5 | IMPROVED_BG_FIXED | 386 | 727 | 222 | 0.289139 |
| 2 | 1 | IMPROVED_BG_FIXED | 243 | 450 | 163 | 0.283879 |
| 2 | 2.5 | IMPROVED_BG_FIXED | 116 | 267 | 103 | 0.238683 |
| 2 | 5 | IMPROVED_BG_FIXED | 59 | 159 | 105 | 0.182663 |
| 2 | 10 | IMPROVED_BG_FIXED | 24 | 55 | 88 | 0.143713 |
| 2 | 0.1 | CONSERVATIVE_SEDIMENTATION | 745 | 922 | 472 | 0.348294 |
| 2 | 0.5 | CONSERVATIVE_SEDIMENTATION | 407 | 706 | 232 | 0.302602 |
| 2 | 1 | CONSERVATIVE_SEDIMENTATION | 268 | 425 | 180 | 0.306987 |
| 2 | 2.5 | CONSERVATIVE_SEDIMENTATION | 136 | 247 | 116 | 0.272545 |
| 2 | 5 | CONSERVATIVE_SEDIMENTATION | 63 | 155 | 103 | 0.196262 |
| 2 | 10 | CONSERVATIVE_SEDIMENTATION | 26 | 53 | 87 | 0.156627 |
| 3 | 0.1 | ORIGINAL | 786 | 796 | 817 | 0.327637 |
| 3 | 0.5 | ORIGINAL | 453 | 705 | 464 | 0.279285 |
| 3 | 1 | ORIGINAL | 327 | 520 | 299 | 0.285340 |
| 3 | 2.5 | ORIGINAL | 202 | 370 | 207 | 0.259307 |
| 3 | 5 | ORIGINAL | 85 | 260 | 179 | 0.162214 |
| 3 | 10 | ORIGINAL | 21 | 111 | 126 | 0.081395 |
| 3 | 0.1 | IMPROVED_BG_FIXED | 771 | 811 | 818 | 0.321250 |
| 3 | 0.5 | IMPROVED_BG_FIXED | 448 | 710 | 462 | 0.276543 |
| 3 | 1 | IMPROVED_BG_FIXED | 324 | 523 | 306 | 0.281006 |
| 3 | 2.5 | IMPROVED_BG_FIXED | 201 | 371 | 197 | 0.261378 |
| 3 | 5 | IMPROVED_BG_FIXED | 88 | 257 | 174 | 0.169557 |
| 3 | 10 | IMPROVED_BG_FIXED | 21 | 111 | 122 | 0.082677 |
| 3 | 0.1 | CONSERVATIVE_SEDIMENTATION | 815 | 767 | 928 | 0.324701 |
| 3 | 0.5 | CONSERVATIVE_SEDIMENTATION | 481 | 677 | 566 | 0.279002 |
| 3 | 1 | CONSERVATIVE_SEDIMENTATION | 349 | 498 | 417 | 0.276108 |
| 3 | 2.5 | CONSERVATIVE_SEDIMENTATION | 205 | 367 | 213 | 0.261146 |
| 3 | 5 | CONSERVATIVE_SEDIMENTATION | 95 | 250 | 179 | 0.181298 |
| 3 | 10 | CONSERVATIVE_SEDIMENTATION | 22 | 110 | 116 | 0.088710 |
| 4 | 0.1 | ORIGINAL | 810 | 810 | 822 | 0.331695 |
| 4 | 0.5 | ORIGINAL | 491 | 731 | 538 | 0.278977 |
| 4 | 1 | ORIGINAL | 361 | 581 | 448 | 0.259712 |
| 4 | 2.5 | ORIGINAL | 167 | 424 | 336 | 0.180151 |
| 4 | 5 | ORIGINAL | 66 | 278 | 231 | 0.114783 |
| 4 | 10 | ORIGINAL | 18 | 147 | 121 | 0.062937 |
| 4 | 0.1 | IMPROVED_BG_FIXED | 783 | 837 | 827 | 0.319984 |
| 4 | 0.5 | IMPROVED_BG_FIXED | 483 | 739 | 527 | 0.276158 |
| 4 | 1 | IMPROVED_BG_FIXED | 346 | 596 | 427 | 0.252739 |
| 4 | 2.5 | IMPROVED_BG_FIXED | 170 | 421 | 330 | 0.184582 |
| 4 | 5 | IMPROVED_BG_FIXED | 67 | 277 | 225 | 0.117750 |
| 4 | 10 | IMPROVED_BG_FIXED | 11 | 154 | 126 | 0.037801 |
| 4 | 0.1 | CONSERVATIVE_SEDIMENTATION | 870 | 750 | 924 | 0.341981 |
| 4 | 0.5 | CONSERVATIVE_SEDIMENTATION | 529 | 693 | 592 | 0.291621 |
| 4 | 1 | CONSERVATIVE_SEDIMENTATION | 373 | 569 | 491 | 0.260293 |
| 4 | 2.5 | CONSERVATIVE_SEDIMENTATION | 170 | 421 | 365 | 0.177824 |
| 4 | 5 | CONSERVATIVE_SEDIMENTATION | 63 | 281 | 247 | 0.106599 |
| 4 | 10 | CONSERVATIVE_SEDIMENTATION | 12 | 153 | 128 | 0.040956 |
| 5 | 0.1 | ORIGINAL | 796 | 901 | 726 | 0.328518 |
| 5 | 0.5 | ORIGINAL | 452 | 777 | 557 | 0.253080 |
| 5 | 1 | ORIGINAL | 323 | 602 | 485 | 0.229078 |
| 5 | 2.5 | ORIGINAL | 195 | 378 | 329 | 0.216186 |
| 5 | 5 | ORIGINAL | 104 | 226 | 238 | 0.183099 |
| 5 | 10 | ORIGINAL | 45 | 123 | 107 | 0.163636 |
| 5 | 0.1 | IMPROVED_BG_FIXED | 789 | 908 | 735 | 0.324424 |
| 5 | 0.5 | IMPROVED_BG_FIXED | 480 | 749 | 566 | 0.267409 |
| 5 | 1 | IMPROVED_BG_FIXED | 337 | 588 | 496 | 0.237157 |
| 5 | 2.5 | IMPROVED_BG_FIXED | 211 | 362 | 342 | 0.230601 |
| 5 | 5 | IMPROVED_BG_FIXED | 110 | 220 | 223 | 0.198915 |
| 5 | 10 | IMPROVED_BG_FIXED | 48 | 120 | 100 | 0.179104 |
| 5 | 0.1 | CONSERVATIVE_SEDIMENTATION | 867 | 830 | 789 | 0.348753 |
| 5 | 0.5 | CONSERVATIVE_SEDIMENTATION | 516 | 713 | 626 | 0.278167 |
| 5 | 1 | CONSERVATIVE_SEDIMENTATION | 345 | 580 | 531 | 0.236951 |
| 5 | 2.5 | CONSERVATIVE_SEDIMENTATION | 219 | 354 | 367 | 0.232979 |
| 5 | 5 | CONSERVATIVE_SEDIMENTATION | 122 | 208 | 262 | 0.206081 |
| 5 | 10 | CONSERVATIVE_SEDIMENTATION | 54 | 114 | 129 | 0.181818 |
| 6 | 0.1 | ORIGINAL | 939 | 695 | 889 | 0.372176 |
| 6 | 0.5 | ORIGINAL | 646 | 603 | 624 | 0.344901 |
| 6 | 1 | ORIGINAL | 505 | 463 | 479 | 0.348998 |
| 6 | 2.5 | ORIGINAL | 325 | 286 | 304 | 0.355191 |
| 6 | 5 | ORIGINAL | 155 | 193 | 243 | 0.262267 |
| 6 | 10 | ORIGINAL | 51 | 73 | 155 | 0.182796 |
| 6 | 0.1 | IMPROVED_BG_FIXED | 908 | 726 | 866 | 0.363200 |
| 6 | 0.5 | IMPROVED_BG_FIXED | 635 | 614 | 637 | 0.336691 |
| 6 | 1 | IMPROVED_BG_FIXED | 494 | 474 | 508 | 0.334688 |
| 6 | 2.5 | IMPROVED_BG_FIXED | 309 | 302 | 320 | 0.331901 |
| 6 | 5 | IMPROVED_BG_FIXED | 168 | 180 | 226 | 0.292683 |
| 6 | 10 | IMPROVED_BG_FIXED | 65 | 59 | 149 | 0.238095 |
| 6 | 0.1 | CONSERVATIVE_SEDIMENTATION | 985 | 649 | 915 | 0.386426 |
| 6 | 0.5 | CONSERVATIVE_SEDIMENTATION | 660 | 589 | 682 | 0.341792 |
| 6 | 1 | CONSERVATIVE_SEDIMENTATION | 515 | 453 | 576 | 0.333549 |
| 6 | 2.5 | CONSERVATIVE_SEDIMENTATION | 339 | 272 | 399 | 0.335644 |
| 6 | 5 | CONSERVATIVE_SEDIMENTATION | 163 | 185 | 287 | 0.256693 |
| 6 | 10 | CONSERVATIVE_SEDIMENTATION | 59 | 65 | 179 | 0.194719 |

## Continuous scores

| Lead | Case | MAE mm | RMSE mm |
|---:|---|---:|---:|
| 1 | ORIGINAL | 1.114200 | 4.062290 |
| 1 | IMPROVED_BG_FIXED | 1.100693 | 4.044107 |
| 1 | CONSERVATIVE_SEDIMENTATION | 1.123314 | 4.112423 |
| 2 | ORIGINAL | 1.422697 | 4.673886 |
| 2 | IMPROVED_BG_FIXED | 1.429438 | 4.669778 |
| 2 | CONSERVATIVE_SEDIMENTATION | 1.401460 | 4.607156 |
| 3 | ORIGINAL | 1.787573 | 4.126258 |
| 3 | IMPROVED_BG_FIXED | 1.782785 | 4.141657 |
| 3 | CONSERVATIVE_SEDIMENTATION | 1.819284 | 4.179876 |
| 4 | ORIGINAL | 2.372371 | 5.971780 |
| 4 | IMPROVED_BG_FIXED | 2.427927 | 6.208988 |
| 4 | CONSERVATIVE_SEDIMENTATION | 2.465628 | 6.213075 |
| 5 | ORIGINAL | 2.148212 | 5.371470 |
| 5 | IMPROVED_BG_FIXED | 2.060558 | 5.151253 |
| 5 | CONSERVATIVE_SEDIMENTATION | 2.156191 | 5.128696 |
| 6 | ORIGINAL | 2.366093 | 7.106392 |
| 6 | IMPROVED_BG_FIXED | 2.378503 | 7.109333 |
| 6 | CONSERVATIVE_SEDIMENTATION | 2.544537 | 7.300393 |

## Fixed constraints

| Goal | Lead | Threshold mm | Baseline | Candidate CSI | Baseline CSI | Pass |
|---|---:|---:|---|---:|---:|---|
| preserve_current_B1 | 1 | 0.1 | IMPROVED_BG_FIXED | 0.447788 | 0.429422 | True |
| preserve_current_B1 | 1 | 0.5 | IMPROVED_BG_FIXED | 0.340633 | 0.328443 | True |
| preserve_current_B1 | 1 | 1 | IMPROVED_BG_FIXED | 0.331742 | 0.328883 | True |
| preserve_current_B1 | 1 | 2.5 | IMPROVED_BG_FIXED | 0.384783 | 0.367033 | True |
| preserve_current_B1 | 1 | 5 | IMPROVED_BG_FIXED | 0.326087 | 0.283582 | True |
| preserve_current_B1 | 1 | 10 | IMPROVED_BG_FIXED | 0.075342 | 0.070423 | True |
| recover_low_threshold_vs_ORIGINAL | 2 | 0.1 | ORIGINAL | 0.348294 | 0.338109 | True |
| recover_low_threshold_vs_ORIGINAL | 2 | 0.5 | ORIGINAL | 0.302602 | 0.299623 | True |
| recover_low_threshold_vs_ORIGINAL | 2 | 1 | ORIGINAL | 0.306987 | 0.293286 | True |
| preserve_current_B1 | 2 | 5 | IMPROVED_BG_FIXED | 0.196262 | 0.182663 | True |
| recover_low_threshold_vs_ORIGINAL | 3 | 0.1 | ORIGINAL | 0.324701 | 0.327637 | False |
| recover_low_threshold_vs_ORIGINAL | 3 | 0.5 | ORIGINAL | 0.279002 | 0.279285 | False |
| recover_low_threshold_vs_ORIGINAL | 3 | 1 | ORIGINAL | 0.276108 | 0.285340 | False |
| preserve_current_B1 | 3 | 5 | IMPROVED_BG_FIXED | 0.181298 | 0.169557 | True |
| recover_low_threshold_vs_ORIGINAL | 4 | 0.1 | ORIGINAL | 0.341981 | 0.331695 | True |
| recover_low_threshold_vs_ORIGINAL | 4 | 0.5 | ORIGINAL | 0.291621 | 0.278977 | True |
| recover_low_threshold_vs_ORIGINAL | 4 | 1 | ORIGINAL | 0.260293 | 0.259712 | True |
| preserve_current_B1 | 4 | 5 | IMPROVED_BG_FIXED | 0.106599 | 0.117750 | False |
| recover_low_threshold_vs_ORIGINAL | 5 | 0.1 | ORIGINAL | 0.348753 | 0.328518 | True |
| recover_low_threshold_vs_ORIGINAL | 5 | 0.5 | ORIGINAL | 0.278167 | 0.253080 | True |
| recover_low_threshold_vs_ORIGINAL | 5 | 1 | ORIGINAL | 0.236951 | 0.229078 | True |
| preserve_current_B1 | 5 | 5 | IMPROVED_BG_FIXED | 0.206081 | 0.198915 | True |
| recover_low_threshold_vs_ORIGINAL | 6 | 0.1 | ORIGINAL | 0.386426 | 0.372176 | True |
| recover_low_threshold_vs_ORIGINAL | 6 | 0.5 | ORIGINAL | 0.341792 | 0.344901 | False |
| recover_low_threshold_vs_ORIGINAL | 6 | 1 | ORIGINAL | 0.333549 | 0.348998 | False |
| preserve_current_B1 | 6 | 5 | IMPROVED_BG_FIXED | 0.256693 | 0.292683 | False |

## Point transitions

| Lead | Baseline | Observation subset | Threshold | N | Both below | Gained | Lost | Both above |
|---:|---|---|---:|---:|---:|---:|---:|---:|
| 1 | ORIGINAL | weak_observed | 0.1 | 880 | 606 | 56 | 4 | 214 |
| 1 | ORIGINAL | dry_observed | 0.1 | 2095 | 1992 | 49 | 1 | 53 |
| 1 | ORIGINAL | strong_observed | 5 | 154 | 64 | 16 | 0 | 74 |
| 1 | ORIGINAL | below_strong_observed | 5 | 3534 | 3411 | 8 | 1 | 114 |
| 1 | IMPROVED_BG_FIXED | weak_observed | 0.1 | 880 | 610 | 24 | 0 | 246 |
| 1 | IMPROVED_BG_FIXED | dry_observed | 0.1 | 2095 | 1993 | 16 | 0 | 86 |
| 1 | IMPROVED_BG_FIXED | strong_observed | 5 | 154 | 64 | 14 | 0 | 76 |
| 1 | IMPROVED_BG_FIXED | below_strong_observed | 5 | 3534 | 3411 | 9 | 1 | 113 |
| 2 | ORIGINAL | weak_observed | 0.1 | 974 | 700 | 36 | 3 | 235 |
| 2 | ORIGINAL | dry_observed | 0.1 | 2021 | 1526 | 68 | 23 | 404 |
| 2 | ORIGINAL | strong_observed | 5 | 218 | 155 | 4 | 0 | 59 |
| 2 | ORIGINAL | below_strong_observed | 5 | 3470 | 3362 | 1 | 5 | 102 |
| 2 | IMPROVED_BG_FIXED | weak_observed | 0.1 | 974 | 700 | 44 | 3 | 227 |
| 2 | IMPROVED_BG_FIXED | dry_observed | 0.1 | 2021 | 1535 | 30 | 14 | 442 |
| 2 | IMPROVED_BG_FIXED | strong_observed | 5 | 218 | 155 | 4 | 0 | 59 |
| 2 | IMPROVED_BG_FIXED | below_strong_observed | 5 | 3470 | 3363 | 2 | 4 | 101 |
| 3 | ORIGINAL | weak_observed | 0.1 | 735 | 490 | 25 | 2 | 218 |
| 3 | ORIGINAL | dry_observed | 0.1 | 2106 | 1150 | 139 | 28 | 789 |
| 3 | ORIGINAL | strong_observed | 5 | 345 | 248 | 12 | 2 | 83 |
| 3 | ORIGINAL | below_strong_observed | 5 | 3343 | 3149 | 15 | 15 | 164 |
| 3 | IMPROVED_BG_FIXED | weak_observed | 0.1 | 735 | 491 | 25 | 1 | 218 |
| 3 | IMPROVED_BG_FIXED | dry_observed | 0.1 | 2106 | 1174 | 114 | 4 | 814 |
| 3 | IMPROVED_BG_FIXED | strong_observed | 5 | 345 | 248 | 9 | 2 | 86 |
| 3 | IMPROVED_BG_FIXED | below_strong_observed | 5 | 3343 | 3155 | 14 | 9 | 165 |
| 4 | ORIGINAL | weak_observed | 0.1 | 678 | 409 | 39 | 7 | 223 |
| 4 | ORIGINAL | dry_observed | 0.1 | 2068 | 1118 | 128 | 26 | 796 |
| 4 | ORIGINAL | strong_observed | 5 | 344 | 268 | 10 | 13 | 53 |
| 4 | ORIGINAL | below_strong_observed | 5 | 3344 | 3072 | 41 | 25 | 206 |
| 4 | IMPROVED_BG_FIXED | weak_observed | 0.1 | 678 | 410 | 38 | 6 | 224 |
| 4 | IMPROVED_BG_FIXED | dry_observed | 0.1 | 2068 | 1120 | 121 | 24 | 803 |
| 4 | IMPROVED_BG_FIXED | strong_observed | 5 | 344 | 273 | 4 | 8 | 59 |
| 4 | IMPROVED_BG_FIXED | below_strong_observed | 5 | 3344 | 3076 | 43 | 21 | 204 |
| 5 | ORIGINAL | weak_observed | 0.1 | 772 | 417 | 89 | 11 | 255 |
| 5 | ORIGINAL | dry_observed | 0.1 | 1991 | 1158 | 107 | 44 | 682 |
| 5 | ORIGINAL | strong_observed | 5 | 330 | 202 | 24 | 6 | 98 |
| 5 | ORIGINAL | below_strong_observed | 5 | 3358 | 3058 | 62 | 38 | 200 |
| 5 | IMPROVED_BG_FIXED | weak_observed | 0.1 | 772 | 425 | 89 | 3 | 255 |
| 5 | IMPROVED_BG_FIXED | dry_observed | 0.1 | 1991 | 1160 | 96 | 42 | 693 |
| 5 | IMPROVED_BG_FIXED | strong_observed | 5 | 330 | 197 | 23 | 11 | 99 |
| 5 | IMPROVED_BG_FIXED | below_strong_observed | 5 | 3358 | 3062 | 73 | 34 | 189 |
| 6 | ORIGINAL | weak_observed | 0.1 | 666 | 357 | 63 | 25 | 221 |
| 6 | ORIGINAL | dry_observed | 0.1 | 2054 | 1017 | 148 | 122 | 767 |
| 6 | ORIGINAL | strong_observed | 5 | 348 | 166 | 27 | 19 | 136 |
| 6 | ORIGINAL | below_strong_observed | 5 | 3340 | 3000 | 97 | 53 | 190 |
| 6 | IMPROVED_BG_FIXED | weak_observed | 0.1 | 666 | 365 | 68 | 17 | 216 |
| 6 | IMPROVED_BG_FIXED | dry_observed | 0.1 | 2054 | 1056 | 132 | 83 | 783 |
| 6 | IMPROVED_BG_FIXED | strong_observed | 5 | 348 | 167 | 13 | 18 | 150 |
| 6 | IMPROVED_BG_FIXED | below_strong_observed | 5 | 3340 | 3012 | 102 | 41 | 185 |
