#!/usr/bin/env python3
"""Add compact, read-only C1 process-stage column summaries to prepared source."""
from __future__ import annotations

import argparse
from pathlib import Path


def update(stage: int) -> str:
    return f'''pr99_stage_high = pr99_stage_sum({stage},i)+pr99_stage_value
pr99_stage_back = pr99_stage_high-pr99_stage_sum({stage},i)
pr99_stage_comp({stage},i)=pr99_stage_comp({stage},i)+ &
     (pr99_stage_sum({stage},i)-(pr99_stage_high-pr99_stage_back))+ &
     (pr99_stage_value-pr99_stage_back)
pr99_stage_sum({stage},i)=pr99_stage_high
pr99_stage_l1({stage},i)=pr99_stage_l1({stage},i)+ABS(pr99_stage_value)
pr99_stage_max({stage},i)=MAX(pr99_stage_max({stage},i),ABS(pr99_stage_value))
pr99_stage_count({stage},i)=pr99_stage_count({stage},i)+1'''


def update_packet(stage: int, expression: str) -> str:
    return f'''pr99_packet_value={expression}
pr99_packet_high=pr99_packet_sum({stage},i)+pr99_packet_value
pr99_packet_back=pr99_packet_high-pr99_packet_sum({stage},i)
pr99_packet_comp({stage},i)=pr99_packet_comp({stage},i)+ &
     (pr99_packet_sum({stage},i)-(pr99_packet_high-pr99_packet_back))+ &
     (pr99_packet_value-pr99_packet_back)
pr99_packet_sum({stage},i)=pr99_packet_high
pr99_packet_l1({stage},i)=pr99_packet_l1({stage},i)+ABS(pr99_packet_value)
pr99_packet_max({stage},i)=MAX(pr99_packet_max({stage},i),ABS(pr99_packet_value))
pr99_packet_count({stage},i)=pr99_packet_count({stage},i)+1'''


def replace_once(source: str, before: str, after: str, label: str) -> str:
    count = source.count(before)
    if count != 1:
        raise ValueError(f"expected one {label} anchor, found {count}")
    return source.replace(before, after, 1)


def prepare(text: str) -> str:
    text = replace_once(text,
        "   integer :: pr85_rf_unit, pr85_rf_ios\n",
        "   integer :: pr85_rf_unit, pr85_rf_ios\n"
        "   integer :: pr99_stage_count(6,its:ite),pr99_stage_unit,pr99_stage_ios,pr99_stage_id\n"
        "   double precision :: pr99_stage_sum(6,its:ite),pr99_stage_comp(6,its:ite)\n"
        "   double precision :: pr99_stage_l1(6,its:ite),pr99_stage_max(6,its:ite)\n"
        "   double precision :: pr99_stage_value,pr99_stage_high,pr99_stage_back\n"
        "   integer :: pr99_packet_count(6,its:ite)\n"
        "   double precision :: pr99_packet_sum(6,its:ite),pr99_packet_comp(6,its:ite)\n"
        "   double precision :: pr99_packet_l1(6,its:ite),pr99_packet_max(6,its:ite)\n"
        "   double precision :: pr99_packet_value,pr99_packet_high,pr99_packet_back\n", "declarations")
    text = replace_once(text, "   pr89_cold_water=0.0d0\n",
        "   pr89_cold_water=0.0d0\n"
        "   pr99_stage_sum=0.0d0\n   pr99_stage_comp=0.0d0\n"
        "   pr99_stage_l1=0.0d0\n   pr99_stage_max=0.0d0\n"
        "   pr99_stage_count=0\n"
        "   pr99_packet_sum=0.0d0\n   pr99_packet_comp=0.0d0\n"
        "   pr99_packet_l1=0.0d0\n   pr99_packet_max=0.0d0\n"
        "   pr99_packet_count=0\n", "initialization")

    melt_anchor = "                  open(newunit=pr85_melt_unit,file='pr85_kdm6_melt_budget.raw', &"
    text = replace_once(text, melt_anchor,
        "                  pr99_stage_value=(pr85_melt_qc_delta+pr85_melt_qr_delta+ &\n"
        "                       DBLE(qrs(i,k,2))-DBLE(pr85_melt_q_before))* &\n"
        "                       DBLE(dry_carrier_density(i,k))*DBLE(delz(i,k))\n" +
        update(1) + "\n" + melt_anchor, "melt accumulator")

    freeze_value = "              pr99_stage_value=DBLE(dry_carrier_density(i,k))*DBLE(delz(i,k))* &\n" \
        "                   ((DBLE(qci(i,k,2))-DBLE(pr85_freeze_qi_before))- &\n" \
        "                    (DBLE(pr85_freeze_qc_before)-DBLE(qci(i,k,1))))\n" + update(2) + "\n"
    for label in ("PINU", "PFRZ"):
        freeze_anchor = "              open(newunit=pr85_freeze_unit,file='pr85_kdm6_freezing_budget.raw', &\n" \
            "                   status='unknown',position='append',action='write',iostat=pr85_freeze_ios)\n" \
            "              if (pr85_freeze_ios.ne.0) error stop 'PR85 freezing ledger open failed'\n" \
            "              write(pr85_freeze_unit,'(a,3i8,1x,3l1,1p,25e24.16)',iostat=pr85_freeze_ios) &\n" \
            f"                   '{label}'"
        text = replace_once(text, freeze_anchor, freeze_value + freeze_anchor, f"{label} accumulator")

    rain_freeze_anchor = "              open(newunit=pr85_rf_unit,file='pr85_rain_freezing_budget.raw', &\n"
    rain_freeze_value = "              pr99_stage_value=-DBLE(dry_carrier_density(i,k))*DBLE(delz(i,k))* &\n" \
        "                   ((DBLE(pr85_rf_qr_before)+DBLE(pr85_rf_qg_before))- &\n" \
        "                    (DBLE(qrs(i,k,1))+DBLE(qrs(i,k,3))))\n" + update(6) + "\n"
    text = replace_once(text, rain_freeze_anchor,
                        rain_freeze_value + rain_freeze_anchor, "rain-freezing accumulator")

    cold_anchor = "            if (pr67_trace_this_call) then\n            write(pr85_cold_unit,'(a,8i8,1x,l1,1p,*(1x,e24.16))',iostat=pr85_cold_ios) &"
    cold_expr = "            pr99_stage_value=(DBLE(qci(i,k,1))-(DBLE(rain_q_before(1))+ &\n" \
        "                 DBLE(rain_ng_alpha)*DBLE(rain_ng_q_process(1))+ &\n" \
        "                 DBLE(rain_aut_alpha)*DBLE(rain_aut_q_process(1))+ &\n" \
        "                 DBLE(rain_g_alpha)*DBLE(rain_q_process_request(1))))+ &\n" \
        "                 (DBLE(qci(i,k,2))-(DBLE(rain_q_before(2))+ &\n" \
        "                 DBLE(rain_ng_alpha)*DBLE(rain_ng_q_process(2))+ &\n" \
        "                 DBLE(rain_aut_alpha)*DBLE(rain_aut_q_process(2))+ &\n" \
        "                 DBLE(rain_g_alpha)*DBLE(rain_q_process_request(2))))+ &\n" \
        "                 (DBLE(qrs(i,k,1))-(DBLE(rain_q_before(3))+ &\n" \
        "                 DBLE(rain_ng_alpha)*DBLE(rain_ng_q_process(3))+ &\n" \
        "                 DBLE(rain_aut_alpha)*DBLE(rain_aut_q_process(3))+ &\n" \
        "                 DBLE(rain_g_alpha)*DBLE(rain_q_process_request(3))))+ &\n" \
        "                 (DBLE(qrs(i,k,2))-(DBLE(rain_q_before(4))+ &\n" \
        "                 DBLE(rain_ng_alpha)*DBLE(rain_ng_q_process(4))+ &\n" \
        "                 DBLE(rain_aut_alpha)*DBLE(rain_aut_q_process(4))+ &\n" \
        "                 DBLE(rain_g_alpha)*DBLE(rain_q_process_request(4))))+ &\n" \
        "                 (DBLE(qrs(i,k,3))-(DBLE(rain_q_before(5))+ &\n" \
        "                 DBLE(rain_ng_alpha)*DBLE(rain_ng_q_process(5))+ &\n" \
        "                 DBLE(rain_aut_alpha)*DBLE(rain_aut_q_process(5))+ &\n" \
        "                 DBLE(rain_g_alpha)*DBLE(rain_q_process_request(5))))+ &\n" \
        "                 (DBLE(q(i,k))-(DBLE(rain_qv_before)+ &\n" \
        "                 DBLE(rain_ng_alpha)*DBLE(rain_ng_qv_process)+ &\n" \
        "                 DBLE(rain_g_alpha)*DBLE(rain_g_qv_process)))\n" \
        "            pr99_stage_value=pr99_stage_value*DBLE(dry_carrier_density(i,k))*DBLE(delz(i,k))\n" + update(3) + "\n" + update_packet(3,
            "(DBLE(rain_ng_alpha)*(SUM(DBLE(rain_ng_q_process))+DBLE(rain_ng_qv_process))+ &\n"
            " DBLE(rain_aut_alpha)*SUM(DBLE(rain_aut_q_process))+ &\n"
            " DBLE(rain_g_alpha)*(SUM(DBLE(rain_q_process_request))+DBLE(rain_g_qv_process)))* &\n"
            " DBLE(dry_carrier_density(i,k))*DBLE(delz(i,k))") + "\n" + cold_anchor
    text = replace_once(text, cold_anchor, cold_expr, "cold accumulator")
    # Remove the known full-tile trace trigger from the verbose cold/warm row writers.
    text = replace_once(text, "            if (pr67_trace_this_call) then\n            write(pr85_cold_unit,", "            if (.false.) then\n            write(pr85_cold_unit,", "cold raw suppression")

    warm_anchor = "            if (rain_warm_search_status.eq.1 .or. rain_warm_retry.gt.0 .or. &\n                pr67_trace_this_call) then\n            write(pr85_warm_unit,"
    warm_expr = "            pr99_stage_value=SUM(DBLE(rain_warm_q_after)-DBLE(rain_q_before)- &\n" \
        "                 DBLE(rain_warm_alpha)*DBLE(rain_warm_q_process))+ &\n" \
        "                 (DBLE(rain_warm_qv_after)-DBLE(rain_qv_before)- &\n" \
        "                 DBLE(rain_warm_alpha)*DBLE(rain_warm_qv_process))\n" \
        "            pr99_stage_value=pr99_stage_value*DBLE(dry_carrier_density(i,k))*DBLE(delz(i,k))\n" + update(4) + "\n" + update_packet(4,
            "(DBLE(rain_warm_alpha)*(SUM(DBLE(rain_warm_q_process))+DBLE(rain_warm_qv_process)))* &\n"
            " DBLE(dry_carrier_density(i,k))*DBLE(delz(i,k))") + "\n" + warm_anchor
    text = replace_once(text, warm_anchor, warm_expr, "warm accumulator")
    text = replace_once(text, "rain_warm_search_status.eq.1 .or. rain_warm_retry.gt.0 .or. &\n                pr67_trace_this_call", "rain_warm_search_status.eq.1 .or. rain_warm_retry.gt.0", "warm raw suppression")

    transition_after = "             pr85_trace_snow_gain = dble(qrs(i,k,2))-dble(pr85_trace_qs)\n"
    text = replace_once(text, transition_after, transition_after +
        "             pr99_stage_value=(pr85_trace_snow_gain-pr85_trace_removed_qi)* &\n"
        "                  DBLE(dry_carrier_density(i,k))*DBLE(delz(i,k))\n" + update(5) + "\n", "transition accumulator")

    out_anchor = "   call liquid_end(lat,its,ite)\n"
    output = "   open(newunit=pr99_stage_unit,file='pr99_process_stage_compact.raw', &\n" \
        "        form='formatted',status='unknown',position='append',action='write',iostat=pr99_stage_ios)\n" \
        "   if (pr99_stage_ios.ne.0) error stop 'PR99 stage compact open failed'\n" \
        "   do i=its,ite\n" \
        "     do pr99_stage_id=1,6\n" \
        "       write(pr99_stage_unit,'(a,3i8,2i12,1p,6e24.16)',iostat=pr99_stage_ios) 'PR99_STAGE_COLUMN', &\n" \
        "            i,lat,pr99_stage_id,pr99_stage_count(pr99_stage_id,i),pr99_packet_count(pr99_stage_id,i), &\n" \
        "            pr99_stage_sum(pr99_stage_id,i)+pr99_stage_comp(pr99_stage_id,i), &\n" \
        "            pr99_stage_l1(pr99_stage_id,i),pr99_stage_max(pr99_stage_id,i), &\n" \
        "            pr99_packet_sum(pr99_stage_id,i)+pr99_packet_comp(pr99_stage_id,i), &\n" \
        "            pr99_packet_l1(pr99_stage_id,i),pr99_packet_max(pr99_stage_id,i)\n" \
        "       if (pr99_stage_ios.ne.0) error stop 'PR99 stage compact write failed'\n" \
        "     enddo\n" \
        "   enddo\n" \
        "   close(pr99_stage_unit,iostat=pr99_stage_ios)\n" \
        "   if (pr99_stage_ios.ne.0) error stop 'PR99 stage compact close failed'\n" + out_anchor
    text = replace_once(text, out_anchor, output, "compact output")
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(prepare(args.source.read_text()))


if __name__ == "__main__":
    main()
