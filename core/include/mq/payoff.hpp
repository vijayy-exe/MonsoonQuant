// Payoff transform applied to the simulated terminal index (SPEC §7.1,
// §7.4's SimRequest.payoff field).
//
// For RAINCHNNAI/RAINMUMBAI the Final Settlement Price *is* the CDR
// index value on expiry day (SPEC §7.1, settlement.method) — there is
// no separate strike/payout structure the way an option or a
// parametric cover product would have. identity_payoff below is that
// fact made explicit in code, not a placeholder standing in for a
// transform that hasn't been written yet. A real transform (e.g. for
// SPEC's F17 parametric cover designer, M11) would plug in here
// without needing any change to simulate.cpp's loop.
#pragma once

namespace mq {

inline double identity_payoff(double terminal_index) { return terminal_index; }

} // namespace mq
