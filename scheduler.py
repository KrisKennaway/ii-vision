"""Opcode schedulers."""

import collections
from typing import Iterator

import opcodes
import random


class OpcodeScheduler:
    def schedule(self, changes) -> Iterator[opcodes.Opcode]:
        raise NotImplementedError


def nonce():
    return random.randint(0, 255)


class HeuristicPageFirstScheduler(OpcodeScheduler):
    """Group by page first then content byte.

    Grouping by page (rather than content) means that we'll reduce the window
    of time during which we have violated a colour invariant due to bits
    hanging across byte boundaries.
    """

    # Median similarity: 0.862798 @ 15 fps, 10M output
    def schedule(self, changes):
        data = {}

        page_weights = collections.defaultdict(int)
        page_content_weights = {}
        for ch in changes:
            xor_weight, page, offset, content, run_length = ch
            data.setdefault((page, content), list()).append(
                (xor_weight, run_length, offset))
            page_weights[page] += xor_weight
            page_content_weights.setdefault(page, collections.defaultdict(
                int))[content] += xor_weight

        # Weight each page and content within page by total xor weight and
        # traverse in this order, with a random nonce so that we don't
        # consistently prefer higher-valued pages etc.

        pages = sorted(
            list(page_weights.keys()),
            key=lambda p: (page_weights[p], nonce()), reverse=True)
        for page in pages:
            yield opcodes.SetPage(page)

            content_weights = page_content_weights[page]
            contents = sorted(
                list(content_weights.keys()),
                key=lambda c: (content_weights[c], nonce()),
                reverse=True)

            for content in contents:
                yield opcodes.SetContent(content)
                offsets = sorted(
                    data[(page, content)],
                    key=lambda x: (x[0], nonce()),
                    reverse=True)

                # print("page %d content %d offsets %s" % (page, content,
                #                                         offsets))
                for (_, run_length, offset) in offsets:
                    if run_length > 1:
                        # print("Offset %d run length %d" % (
                        #     offset, run_length))
                        yield opcodes.RLE(offset, run_length)
                    else:
                        yield opcodes.Store(offset)



class HeuristicContentFirstScheduler(OpcodeScheduler):
    """Group by content first then page.

    This has a fair bit of colour fringing because we aren't guaranteed to
    get back to fixing up hanging bits within our frame window.  In practise
    this also does not deal well with fine detail at higher frame rates.
    """

    def schedule(self, changes):
        data = {}

        content_weights = collections.defaultdict(int)
        content_page_weights = {}
        for ch in changes:
            xor_weight, page, offset, content, run_length = ch
            data.setdefault((page, content), list()).append(
                (xor_weight, run_length, offset))
            content_weights[content] += xor_weight
            content_page_weights.setdefault(content, collections.defaultdict(
                int))[page] += xor_weight

        # Weight each page and content within page by total xor weight and
        # traverse in this order

        contents = sorted(
            list(content_weights.keys()),
            key=lambda p: content_weights[p], reverse=True)
        for content in contents:
            yield opcodes.SetContent(content)

            page_weights = content_page_weights[content]

            pages = sorted(
                list(page_weights.keys()),
                key=lambda c: page_weights[c],
                reverse=True)
            for page in pages:
                yield opcodes.SetPage(page)
                offsets = sorted(data[(page, content)], key=lambda x: x[0],
                                 reverse=True)

                # print("page %d content %d offsets %s" % (page, content,
                #                                        offsets))
                for (_, run_length, offset) in offsets:
                    if run_length > 1:
                        # print("Offset %d run length %d" % (
                        #     offset, run_length))
                        yield opcodes.RLE(offset, run_length)
                    else:
                        yield opcodes.Store(offset)


class OldHeuristicPageFirstScheduler(OpcodeScheduler):
    """Group by page first then content byte.

    This uses a deterministic order of pages and content bytes, and ignores
    xor_weight altogether
    """

    # Median similarity: 0.854613 ( @ 15 fps, 10M output)
    # is almost as good as HeuristicPageFirstScheduler -- despite the fact
    # that we consistently fail to update some pages.  That means we should
    # be measuring some notion of error persistence rather than just
    # similarity

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
                        yield opcodes.Store(offset)

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
