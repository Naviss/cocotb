# Copyright cocotb contributors
# Licensed under the Revised BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-3-Clause
"""
Tests for edge triggers

* Edge
* RisingEdge
* FallingEdge
* ClockCycles
"""

import os
import re

import pytest

import cocotb
from cocotb._sim_versions import RivieraVersion
from cocotb.clock import Clock
from cocotb.result import SimTimeoutError
from cocotb.triggers import (
    ClockCycles,
    Combine,
    Edge,
    FallingEdge,
    First,
    ReadOnly,
    RisingEdge,
    Timer,
    with_timeout,
)

LANGUAGE = os.environ["TOPLEVEL_LANG"].lower().strip()


async def count_edges_cycles(signal, edges):
    edge = RisingEdge(signal)
    for i in range(edges):
        await edge
        signal._log.info("Rising edge %d detected" % i)
    signal._log.info("Finished, returning %d" % edges)
    return edges


async def do_single_edge_check(dut, level):
    """Do test for rising edge"""
    old_value = dut.clk.value
    dut._log.info("Value of %s is %d" % (dut.clk._path, old_value))
    assert old_value != level
    if level == 1:
        await RisingEdge(dut.clk)
    else:
        await FallingEdge(dut.clk)
    new_value = dut.clk.value
    dut._log.info("Value of %s is %d" % (dut.clk._path, new_value))
    assert new_value == level, "%s not %d at end" % (dut.clk._path, level)


@cocotb.test()
async def test_rising_edge(dut):
    """Test that a rising edge can be awaited on"""
    dut.clk.value = 0
    await Timer(1, "ns")
    test = cocotb.start_soon(do_single_edge_check(dut, 1))
    await Timer(10, "ns")
    dut.clk.value = 1
    fail_timer = Timer(1000, "ns")
    result = await First(fail_timer, test.join())
    assert result is not fail_timer, "Test timed out"


@cocotb.test()
async def test_falling_edge(dut):
    """Test that a falling edge can be awaited on"""
    dut.clk.value = 1
    await Timer(1, "ns")
    test = cocotb.start_soon(do_single_edge_check(dut, 0))
    await Timer(10, "ns")
    dut.clk.value = 0
    fail_timer = Timer(1000, "ns")
    result = await First(fail_timer, test.join())
    assert result is not fail_timer, "Test timed out"


@cocotb.test()
async def test_either_edge(dut):
    """Test that either edge can be triggered on"""
    dut.clk.value = 0
    await Timer(1, "ns")
    dut.clk.value = 1
    await Edge(dut.clk)
    assert dut.clk.value == 1
    await Timer(10, "ns")
    dut.clk.value = 0
    await Edge(dut.clk)
    assert dut.clk.value == 0
    await Timer(10, "ns")
    dut.clk.value = 1
    await Edge(dut.clk)
    assert dut.clk.value == 1
    await Timer(10, "ns")
    dut.clk.value = 0
    await Edge(dut.clk)
    assert dut.clk.value == 0
    await Timer(10, "ns")
    dut.clk.value = 1
    await Edge(dut.clk)
    assert dut.clk.value == 1
    await Timer(10, "ns")
    dut.clk.value = 0
    await Edge(dut.clk)
    assert dut.clk.value == 0


@cocotb.test()
async def test_fork_and_monitor(dut, period=1000, clocks=6):
    cocotb.start_soon(Clock(dut.clk, period, "ns").start())

    # Ensure the clock has started
    await RisingEdge(dut.clk)

    timer = Timer(period + 10, "ns")
    task = cocotb.start_soon(count_edges_cycles(dut.clk, clocks))
    count = 0
    expect = clocks - 1

    while True:
        result = await First(timer, task)
        assert count <= expect, "Task didn't complete in expected time"
        if result is timer:
            dut._log.info("Count %d: Task still running" % count)
            count += 1
        else:
            break
    assert count == expect, "Expected to monitor the task %d times but got %d" % (
        expect,
        count,
    )
    assert result == clocks, "Expected task to return %d but got %s" % (
        clocks,
        repr(result),
    )


async def do_clock(dut, limit, period):
    """Simple clock with a limit"""
    wait_period = period / 2
    while limit:
        await Timer(wait_period, "ns")
        dut.clk.value = 0
        await Timer(wait_period, "ns")
        dut.clk.value = 1
        limit -= 1


async def do_edge_count(dut, signal):
    """Count the edges"""
    global edges_seen
    while True:
        await RisingEdge(signal)
        edges_seen += 1


@cocotb.test()
async def test_edge_count(dut):
    """Count the number of edges is as expected"""
    global edges_seen
    edges_seen = 0
    clk_period = 100
    edge_count = 10
    cocotb.start_soon(do_clock(dut, edge_count, clk_period))
    cocotb.start_soon(do_edge_count(dut, dut.clk))

    await Timer(clk_period * (edge_count + 1), "ns")
    assert edge_count == edges_seen, "Correct edge count failed - saw %d, wanted %d" % (
        edges_seen,
        edge_count,
    )


@cocotb.test()
async def test_edge_identity(dut):
    """
    Test that Edge triggers returns the same object each time
    """

    re = RisingEdge(dut.clk)
    fe = FallingEdge(dut.clk)
    e = Edge(dut.clk)

    assert re is RisingEdge(dut.clk)
    assert fe is FallingEdge(dut.clk)
    assert e is Edge(dut.clk)

    # check they are all unique
    assert len({re, fe, e}) == 3
    await Timer(1, "ns")


@cocotb.test()
async def test_singleton_isinstance(dut):
    """
    Test that the result of trigger expression have a predictable type
    """
    assert isinstance(RisingEdge(dut.clk), RisingEdge)
    assert isinstance(FallingEdge(dut.clk), FallingEdge)
    assert isinstance(Edge(dut.clk), Edge)

    await Timer(1, "ns")


@cocotb.test()
async def test_clock_cycles(dut):
    """
    Test the ClockCycles Trigger
    """
    clk = dut.clk
    cocotb.start_soon(Clock(clk, 100, "ns").start())
    await RisingEdge(clk)
    dut._log.info("After one edge")
    t = ClockCycles(clk, 10)
    # NVC gives upper-case identifiers for some things. See gh-3985
    assert re.match(
        r"ClockCycles\(LogicObject\((sample_module|SAMPLE_MODULE).clk\), 10\)", repr(t)
    )
    await t
    dut._log.info("After 10 rising edges")
    t = ClockCycles(clk, 10, rising=False)
    assert re.match(
        r"ClockCycles\(LogicObject\((sample_module|SAMPLE_MODULE).clk\), 10, rising=False\)",
        repr(t),
    )
    await t
    dut._log.info("After 10 falling edges")


@cocotb.test()
async def test_clock_cycles_forked(dut):
    """Test that ClockCycles can be used in forked coroutines"""
    # gh-520

    cocotb.start_soon(Clock(dut.clk, 100, "ns").start())

    async def wait_ten():
        await ClockCycles(dut.clk, 10)

    a = cocotb.start_soon(wait_ten())
    b = cocotb.start_soon(wait_ten())
    await a.join()
    await b.join()


@cocotb.test(
    timeout_time=100,
    timeout_unit="ns",
    expect_error=(  # gh-2344
        SimTimeoutError
        if (
            LANGUAGE in ["verilog"]
            and cocotb.SIM_NAME.lower().startswith(("riviera", "aldec"))
            and RivieraVersion(cocotb.SIM_VERSION) < RivieraVersion("2023.04")
        )
        else ()
    ),
)
async def test_both_edge_triggers(dut):
    async def wait_rising_edge():
        await RisingEdge(dut.clk)

    async def wait_falling_edge():
        await FallingEdge(dut.clk)

    rising_coro = cocotb.start_soon(wait_rising_edge())
    falling_coro = cocotb.start_soon(wait_falling_edge())
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await Combine(rising_coro, falling_coro)


@cocotb.test()
async def test_edge_on_vector(dut):
    """Test that Edge() triggers on any 0/1 change in a vector"""

    cocotb.start_soon(Clock(dut.clk, 100, "ns").start())

    edge_cnt = 0

    async def wait_edge():
        nonlocal edge_cnt
        while True:
            await Edge(dut.stream_out_data_registered)
            if cocotb.SIM_NAME.lower().startswith("modelsim"):
                await ReadOnly()  # not needed for other simulators
            edge_cnt = edge_cnt + 1

    dut.stream_in_data.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    cocotb.start_soon(wait_edge())

    for val in range(1, 2 ** len(dut.stream_in_data) - 1):
        # produce an edge by setting a value != 0:
        dut.stream_in_data.value = val
        await RisingEdge(dut.clk)
        # set back to all-0:
        dut.stream_in_data.value = 0
        await RisingEdge(dut.clk)

    # We have to wait because we don't know the scheduling order of the above
    # Edge(dut.stream_out_data_registered) and the above RisingEdge(dut.clk)
    # Edge(dut.stream_out_data_registered) should occur strictly after RisingEdge(dut.clk),
    # but NVC and Verilator behave differently.
    await RisingEdge(dut.clk)

    expected_count = 2 * ((2 ** len(dut.stream_in_data) - 1) - 1)

    assert edge_cnt == expected_count


@cocotb.test()
async def test_edge_bad_handles(dut):
    with pytest.raises(TypeError):
        RisingEdge(dut)

    with pytest.raises(TypeError):
        FallingEdge(dut)

    with pytest.raises(TypeError):
        Edge(dut)

    with pytest.raises(TypeError):
        RisingEdge(dut.stream_in_data)

    with pytest.raises(TypeError):
        FallingEdge(dut.stream_in_data)


@cocotb.test()
async def test_edge_logic_vector(dut):
    dut.stream_in_data.value = 0

    async def change_stream_in_data():
        await Timer(10, "ns")
        dut.stream_in_data.value = 10

    cocotb.start_soon(change_stream_in_data())

    await with_timeout(Edge(dut.stream_in_data), 20, "ns")


# icarus doesn't support integer inputs/outputs
@cocotb.test(skip=cocotb.SIM_NAME.lower().startswith("icarus"))
async def test_edge_non_logic_handles(dut):
    dut.stream_in_int.value = 0

    async def change_stream_in_int():
        await Timer(10, "ns")
        dut.stream_in_int.value = 10

    cocotb.start_soon(change_stream_in_int())

    await with_timeout(Edge(dut.stream_in_int), 20, "ns")


@cocotb.test()
async def test_edge_trigger_repr(dut):
    e = Edge(dut.clk)
    # NVC gives upper-case identifiers for some things. See gh-3985
    assert re.match(
        r"Edge\(LogicObject\((sample_module|SAMPLE_MODULE).clk\)\)", repr(e)
    )
    e = RisingEdge(dut.stream_in_ready)
    assert re.match(
        r"RisingEdge\(LogicObject\((sample_module|SAMPLE_MODULE).stream_in_ready\)\)",
        repr(e),
    )
    e = FallingEdge(dut.stream_in_valid)
    assert re.match(
        r"FallingEdge\(LogicObject\((sample_module|SAMPLE_MODULE).stream_in_valid\)\)",
        repr(e),
    )
