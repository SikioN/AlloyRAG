#!/bin/bash

NAMESPACE=rag
helm uninstall alloyrag --namespace $NAMESPACE
