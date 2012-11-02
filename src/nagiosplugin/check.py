# Copyright (c) 2012 gocept gmbh & co. kg
# See also LICENSE.txt

"""Central logic for check execution.

The check object controls the domain logic. Interfacing with the
outside system is done via a separate :class:`Runtime` object.
"""

from .context import Context, Contexts
from .error import CheckError
from .resource import Resource
from .result import Result, Results
from .runtime import Runtime
from .state import Ok, Unknown
from .summary import Summary
import logging


class Check(object):
    """Main controller object.

    A Check instance controls the various stages of check execution.
    Specialized objects representing resources, contexts and a summary
    are expected to be passed to the constructor. Alternatively, objects
    can be added later using the :py:meth:`add` method.

    When a check is called, a check probes all resources and evaluates
    the returned metrics to results and performance data. A typical
    usage pattern would be to populate a check with domain objects and
    then call :meth:`main` to delegate control::

        check = Check(... domain objects ...)
        check.main()
    """

    def __init__(self, *objects):
        self.resources = []
        self.contexts = Contexts()
        self.summary = Summary()
        self.results = Results()
        self.perfdata = []
        self.name = ''
        self.add(*objects)

    def add(self, *objects):
        """Add domain objects to a check.

        :param objects: one or more objects that are descendants from
            :class:`Resource`, :class:`Context`,
            :class:`Summary`, or :class:`Results`.
        """
        for obj in objects:
            if isinstance(obj, Resource):
                self.resources.append(obj)
                if not self.name:
                    self.name = self.resources[0].name
            elif isinstance(obj, Context):
                self.contexts.add(obj)
            elif isinstance(obj, Summary):
                self.summary = obj
            elif isinstance(obj, Results):
                self.results = obj
            else:
                raise TypeError('cannot add type {} to check'.format(
                    type(obj)), obj)
        return self

    def _evaluate_resource(self, resource):
        try:
            metric = None
            metrics = resource.probe()
            if not metrics:
                logging.warning('resource %s did not produce any metric',
                                resource.name)
            for metric in metrics:
                context = self.contexts[metric.context]
                metric = metric.replace(contextobj=context, resource=resource)
                self.results.add(metric.evaluate())
                self.perfdata.append(str(metric.performance() or ''))
        except CheckError as e:
            self.results.add(Result(Unknown, str(e), metric))

    def __call__(self):
        """Actually run the check.

        After a check has been called, the :attr:`results` and
        :attr:`perfdata` attributes are populated with the outcomes. In
        most cases, you should not use __call__ directly but invoke
        :meth:`main`, which delegates check execution to the
        :class:`Runtime` environment.
        """
        for resource in self.resources:
            self._evaluate_resource(resource)
        self.perfdata = sorted([p for p in self.perfdata if p])

    def main(self, verbose=1, timeout=10):
        """All-in-one control delegation to the runtime environment.

        Get a :class:`Runtime` instance and perform all phases: run the
        check (via :meth:`__call__`), print results and exit the program
        with an appropriate status code.

        :param verbose: output verbosity level between 0 and 3
        :param timeout: abort check execution with :exc:`Timeout` after
            so many seconds
        """
        runtime = Runtime()
        runtime.execute(self, verbose, timeout)

    @property
    def state(self):
        """Overall check state.

        The most significant (=worst) state seen in :attr:`results` to
        far. :obj:`Unknown` if no results have been collected yet.
        Corresponds with :attr:`exitcode`.
        """
        try:
            return self.results.most_significant_state
        except ValueError:
            return Unknown

    @property
    def summary_str(self):
        """Status line summary string.

        The first line of output that summarizes that situation as
        perceived by the check. The string is usually queried from a
        :class:`Summary` object.
        """
        if self.state == Ok:
            return self.summary.ok(self.results) or ''
        return self.summary.problem(self.results) or ''

    @property
    def verbose_str(self):
        """Additional lines of output.

        Long text output if check runs in verbose mode. Also queried
        from :class:`Summary`.
        """
        return self.summary.verbose(self.results) or ''

    @property
    def exitcode(self):
        """Overall check exit code according to the Nagios API.

        Corresponds with :attr:`state`.
        """
        try:
            return int(self.results.most_significant_state)
        except ValueError:
            return 3
