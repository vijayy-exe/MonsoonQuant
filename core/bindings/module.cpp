#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "mq/params.hpp"
#include "mq/simulate.hpp"

namespace py = pybind11;

PYBIND11_MODULE(mq_core_sim, m) {
  m.doc() =
      "MonsoonQuant C++ chain-dependent rainfall simulator core (SPEC §7.4)";

  py::class_<mq::SimParams>(m, "SimParams")
      .def(py::init<>())
      .def_readwrite("p01", &mq::SimParams::p01)
      .def_readwrite("p11", &mq::SimParams::p11)
      .def_readwrite("mean_amt", &mq::SimParams::mean_amt)
      .def_readwrite("lpa_mm", &mq::SimParams::lpa_mm)
      .def_readwrite("shape", &mq::SimParams::shape)
      .def_readwrite("overdispersion_sd", &mq::SimParams::overdispersion_sd);

  py::class_<mq::SimRequest>(m, "SimRequest")
      .def(py::init<>())
      .def_readwrite("n_paths", &mq::SimRequest::n_paths)
      .def_readwrite("n_days", &mq::SimRequest::n_days)
      .def_readwrite("seed", &mq::SimRequest::seed)
      .def_readwrite("observed_to_date", &mq::SimRequest::observed_to_date)
      .def_readwrite("start_state", &mq::SimRequest::start_state);

  py::class_<mq::SimResult>(m, "SimResult")
      .def_readonly("terminal_index", &mq::SimResult::terminal_index)
      .def_readonly("seasonal_total_mm", &mq::SimResult::seasonal_total_mm);

  m.def("simulate", &mq::simulate,
        "Run the chain-dependent Monte Carlo simulator", py::arg("params"),
        py::arg("request"));

#ifdef _OPENMP
  m.attr("OPENMP_ENABLED") = true;
#else
  m.attr("OPENMP_ENABLED") = false;
#endif
}
