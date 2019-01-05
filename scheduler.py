"""Opcode schedulers."""

from typing import Iterator

import opcodes


class OpcodeScheduler:
    def schedule(self, changes) -> Iterator[opcodes.Opcode]:
        raise NotImplementedError


class HeuristicPageFirstScheduler(OpcodeScheduler):
    """Group by page first then content byte."""

    def schedule(self, changes):
        data = {}
        for ch in changes:
            xor_weight, page, offset, content, run_length = ch
            data.setdefault(page, {}).setdefault(content, set()).add(
                (run_length, offset))

        for page, content_offsets in data.items():
            yield opcodes.SetPage(page)
            for content, offsets in content_offsets.items():
                yield opcodes.SetContent(content)

                # print("page %d content %d offsets %s" % (page, content,
                #                                         offsets))
                for (run_length, offset) in sorted(offsets, reverse=True):
                    if run_length > 1:
                        # print("Offset %d run length %d" % (
                        #     offset, run_length))
                        yield opcodes.RLE(offset, run_length)
                    else:
                        yield opcodes.Offset(offset)

#
# def _tsp_opcode_scheduler(self, changes):
#     # Build distance matrix for pairs of changes based on number of
#     # opcodes it would cost for opcodes to emit target change given source
#
#     dist = np.zeros(shape=(len(changes), len(changes)), dtype=np.int)
#     for i1, ch1 in enumerate(changes):
#         _, page1, _, content1 = ch1
#         for i2, ch2 in enumerate(changes):
#             if ch1 == ch2:
#                 continue
#             _, page2, _, content2 = ch2
#
#             cost = self.CYCLES[0]  # Emit the target content byte
#             if page1 != page2:
#                 cost += self.CYCLES[OpcodeCommand.SET_PAGE]
#             if content1 != content2:
#                 cost += self.CYCLES[OpcodeCommand.SET_CONTENT]
#
#             dist[i1][i2] = cost
#             dist[i2][i1] = cost
#
#     def create_distance_callback(dist_matrix):
#         # Create a callback to calculate distances between cities.
#
#         def distance_callback(from_node, to_node):
#             return int(dist_matrix[from_node][to_node])
#
#         return distance_callback
#
#     routing = pywrapcp.RoutingModel(len(changes), 1, 0)
#     search_parameters = pywrapcp.RoutingModel.DefaultSearchParameters()
#     # Create the distance callback.
#     dist_callback = create_distance_callback(dist)
#     routing.SetArcCostEvaluatorOfAllVehicles(dist_callback)
#
#     assignment = routing.SolveWithParameters(search_parameters)
#     if assignment:
#         # Solution distance.
#         print("Total cycle_counter: " + str(assignment.ObjectiveValue()))
#         # Display the solution.
#         # Only one route here; otherwise iterate from 0 to
#         # routing.vehicles() - 1
#         route_number = 0
#         index = routing.Start(
#             route_number)  # Index of the variable for the starting node.
#         page = 0x20
#         content = 0x7f
#         # TODO: I think this will end by visiting the origin node which
#         #  is not what we want
#         while not routing.IsEnd(index):
#             _, new_page, offset, new_content = changes[index]
#
#             if new_page != page:
#                 page = new_page
#                 yield self._emit(OpcodeCommand.SET_PAGE)
#                 yield page
#
#             if new_content != content:
#                 content = new_content
#                 yield self._emit(OpcodeCommand.SET_CONTENT)
#                 yield content
#
#             self._write(page << 8 | offset, content)
#             yield self._emit(offset)
#
#             index = assignment.Value(routing.NextVar(index))
#     else:
#         raise ValueError('No solution found.')
#
# def _heuristic_opcode_scheduler(self, changes):
#     # Heuristic: group by content byte first then page
#     data = {}
#     for ch in changes:
#         xor_weight, page, offset, content = ch
#         data.setdefault(content, {}).setdefault(page, set()).add(offset)
#
#     for content, page_offsets in data.items():
#         yield self._emit(OpcodeCommand.SET_CONTENT)
#         yield content
#         for page, offsets in page_offsets.items():
#             yield self._emit(OpcodeCommand.SET_PAGE)
#             yield page
#
#             for offset in offsets:
#                 self._write(page << 8 | offset, content)
#                 yield self._emit(offset)
#
