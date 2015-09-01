# coding=utf-8
# Copyright 2015 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import os

from pants.backend.jvm.targets.jvm_target import JvmTarget
from pants.base.build_environment import get_buildroot
from pants.base.exceptions import TaskError
from pants.goal.products import UnionProducts


def _not_excluded_filter(exclude_patterns):
  def not_excluded(path_tuple):
    conf, path = path_tuple
    return not any(excluded in path for excluded in exclude_patterns)
  return not_excluded


class ClasspathProducts(object):
  def __init__(self):
    self._classpaths = UnionProducts()
    self._exclude_patterns = UnionProducts()
    self._buildroot = get_buildroot()

  def add_for_targets(self, targets, classpath_elements):
    """Adds classpath elements to the products of all the provided targets."""
    for target in targets:
      self.add_for_target(target, classpath_elements)

  def add_for_target(self, target, classpath_elements):
    """Adds classpath elements to the products of the provided target."""
    self._validate_classpath_tuples(classpath_elements, target)
    self._classpaths.add_for_target(target, classpath_elements)

  def add_excludes_for_targets(self, targets):
    """Add excludes from the provided targets. Does not look up transitive excludes."""
    for target in targets:
      self._add_excludes_for_target(target)

  def remove_for_target(self, target, classpath_elements):
    """Removes the given entries for the target"""
    self._classpaths.remove_for_target(target, classpath_elements)

  def get_for_target(self, target, transitive=True):
    """Gets the transitive classpath products for the given target, in order, respecting target
       excludes."""
    return self.get_for_targets([target], transitive=transitive)

  def get_for_targets(self, targets, transitive=True):
    """Gets the transitive classpath products for the given targets, in order, respecting target
       excludes."""
    classpath_tuples = self._classpaths.get_for_targets(targets, transitive=transitive)
    filtered_classpath_tuples = self._filter_by_excludes(
      classpath_tuples,
      targets,
      transitive=transitive,
    )
    return filtered_classpath_tuples

  def _filter_by_excludes(self, classpath_tuples, root_targets, transitive):
    exclude_patterns = self._exclude_patterns.get_for_targets(root_targets, transitive=transitive)
    filtered_classpath_tuples = filter(_not_excluded_filter(exclude_patterns),
                                       classpath_tuples)
    return filtered_classpath_tuples

  def _add_excludes_for_target(self, target):
    # TODO(nhoward): replace specific ivy based exclude filterings in the jar object refactor
    # creates strings from excludes that will match classpath entries generated by ivy
    # eg exclude(org='org.example', name='lib') => 'jars/org.example/lib'
    #    exclude(org='org.example')             => 'jars/org.example/'
    # The empty string was added to the end of the os.path.join list, so that the exclude pattern
    # always ends with a path separator. It's a short term fix so we don't match the following
    # 'jars/com.twitter.common/text' in '.../jars/com.twitter.common/text-lang-model/jars/text...'
    if target.is_exported:
      self._exclude_patterns.add_for_target(target,
                                            [os.path.join('jars',
                                                          target.provides.org,
                                                          target.provides.name,
                                                          '')])
    if isinstance(target, JvmTarget) and target.excludes:
      self._exclude_patterns.add_for_target(target,
                                            [os.path.join('jars', e.org, e.name or '', '')
                                             for e in target.excludes])

  def _validate_classpath_tuples(self, classpath, target):
    """Validates that all files are located within the working copy, to simplify relativization."""
    for classpath_tuple in classpath:
      self._validate_path_in_buildroot(classpath_tuple, target)

  def _validate_path_in_buildroot(self, classpath_tuple, target):
    conf, path = classpath_tuple
    if os.path.relpath(path, self._buildroot).startswith(os.pardir):
      raise TaskError(
        'Classpath entry {} for target {} is located outside the buildroot.'
        .format(path, target.address.spec))
