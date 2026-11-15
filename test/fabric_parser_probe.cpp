#include <iomanip>
#include <iostream>
#include <iterator>
#include <sstream>
#include <string>

#include <fabric_parser_xml/xml_parser_plugin.hpp>
#include <rclcpp/rclcpp.hpp>

std::string encode(const std::string & value)
{
  if (value.empty()) {
    return "-";
  }
  std::ostringstream result;
  result << std::hex << std::setfill('0');
  for (const unsigned char character : value) {
    result << std::setw(2) << static_cast<unsigned int>(character);
  }
  return result.str();
}

int main(int argc, char **argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<rclcpp::Node>(
        "fabric_gui_parser_probe", rclcpp::NodeOptions()
    .start_parameter_services(false)
    .start_parameter_event_publisher(false)
    .enable_rosout(false));
  fabric::XMLParser parser;
  parser.initialize(node);
  fabric::Plan plan;
  plan.plan_id = "draft_test";
  plan.plan.assign(std::istreambuf_iterator<char>(std::cin), std::istreambuf_iterator<char>());
  try {
    parser.parse(plan);
    for (const auto &[id, connection] : plan.connections) {
      const auto & source = connection.source;
      std::cout       << "PROBE N " << id << ' ' << encode(source.interface) << ' ' <<
        encode(source.provider)
                      << ' ' << source.instance_id << '\n';
      for (const auto & parameter : source.parameters.options) {
        std::cout         << "PROBE P " << id << ' ' << encode(parameter.key) << ' '
                          << static_cast<int>(parameter.type);
        for (const auto & value : parameter.value) {
          std::cout << ' ' << encode(value);
        }
        std::cout << '\n';
      }
      for (const auto & event : {std::make_pair("start", connection.on_start),
          std::make_pair("success", connection.on_success),
          std::make_pair("failure", connection.on_failure),
          std::make_pair("stop", connection.on_stop)})
      {
        if (event.second.exists()) {
          std::cout           << "PROBE E " << id << ' ' << event.first << ' ' <<
            encode(event.second.interface) << ' '
                              << encode(event.second.provider) << ' ' << event.second.instance_id <<
            '\n';
        }
      }
    }
  } catch (const std::exception & exception) {
    std::cerr << exception.what() << '\n';
    rclcpp::shutdown();
    return 1;
  }
  rclcpp::shutdown();
  return 0;
}
